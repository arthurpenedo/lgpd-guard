"""Demonstração ponta a ponta do proxy com um LLM de verdade (roda no CI).

    cliente ──► lgpd-guard (:8000) ──► espião (:8100) ──► Ollama (:11434)

O espião finge ser o provedor: grava exatamente o que chegou e o que o modelo respondeu,
e repassa para o Ollama. No fim, gera demo/index.html com as quatro visões de cada turno
e falha (código 1) se algum dado pessoal tiver chegado ao "provedor".

Uso: python demo/demo_proxy.py --modelo qwen2.5:1.5b --saida site/demo.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lgpd_guard.proxy import criar_app

OLLAMA = "http://localhost:11434/v1"
SISTEMA = ("Você é a assistente virtual do Banco Aurora. Responda em português, em no máximo duas frases, "
           "e sempre cumprimente o cliente pelo nome.")
TURNOS = [
    "Olá, meu nome é Maria Helena Duarte, CPF 529.982.247-25. Meu cartão 4111 1111 1111 1111 foi clonado, "
    "podem bloquear?",
    "Obrigada! Mandem o cartão novo para a Rua das Flores, 123, CEP 01310-100. Qualquer coisa me liga no "
    "(11) 98765-4321.",
]
DADOS_REAIS = ["Maria Helena", "529.982.247-25", "52998224725", "4111 1111 1111 1111", "Rua das Flores",
               "01310-100", "98765-4321"]

registros: list[dict] = []


def espiao() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def repassar(request: Request) -> JSONResponse:
        corpo = await request.json()
        async with httpx.AsyncClient(timeout=180) as c:
            resp = await c.post(f"{OLLAMA}/chat/completions", json=corpo)
        dados = resp.json()
        registros.append({"recebido": corpo, "respondido": dados["choices"][0]["message"]["content"]})
        return JSONResponse(dados, status_code=resp.status_code)

    return app


def subir(app: FastAPI, porta: int) -> None:
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True).start()
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{porta}/docs", timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"servidor na porta {porta} não subiu")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modelo", default="qwen2.5:1.5b")
    parser.add_argument("--saida", default="demo/index.html")
    args = parser.parse_args()

    subir(espiao(), 8100)
    subir(criar_app(upstream="http://127.0.0.1:8100/v1"), 8000)

    mensagens = [{"role": "system", "content": SISTEMA}]
    sessao, linhas = None, []
    for n, texto in enumerate(TURNOS):
        mensagens.append({"role": "user", "content": texto})
        cab = {"X-Sessao": sessao} if sessao else {}
        r = httpx.post("http://127.0.0.1:8000/v1/chat/completions", headers=cab, timeout=240,
                       json={"model": args.modelo, "messages": mensagens, "temperature": 0, "seed": 42})
        r.raise_for_status()
        sessao = r.headers["X-Sessao"]
        final = r.json()["choices"][0]["message"]["content"]
        mensagens.append({"role": "assistant", "content": final})
        espiado = registros[n]
        linhas.append({
            "cliente_escreveu": texto,
            "provedor_recebeu": espiado["recebido"]["messages"][-1]["content"],
            "provedor_respondeu": espiado["respondido"],
            "cliente_recebeu": final,
            "protegidos": int(r.headers.get("X-Dados-Protegidos", 0)),
        })

    vazou = [d for d in DADOS_REAIS for reg in registros if d in json.dumps(reg["recebido"], ensure_ascii=False)]
    resumo = {"modelo": args.modelo, "turnos": linhas, "dados_que_chegaram_ao_provedor": sorted(set(vazou))}
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).with_suffix(".json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.saida).write_text(pagina(resumo), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    if vazou:
        print(f"FALHA: dados reais chegaram ao provedor: {sorted(set(vazou))}")
        return 1
    print("OK: nenhum dado pessoal chegou ao provedor.")
    return 0


def _marcar(texto: str) -> str:
    import re

    return re.sub(r"&lt;([A-Z_]+_\d+)&gt;", r"<mark>&lt;\1&gt;</mark>", html.escape(texto))


def pagina(resumo: dict) -> str:
    blocos = "".join(f"""
<h2>Turno {i}</h2><div class="grade">
<div class="c"><div class="r">1 · o cliente escreveu</div><pre>{html.escape(t['cliente_escreveu'])}</pre></div>
<div class="c prov"><div class="r">2 · o provedor de IA recebeu</div><pre>{_marcar(t['provedor_recebeu'])}</pre></div>
<div class="c prov"><div class="r">3 · o modelo respondeu</div><pre>{_marcar(t['provedor_respondeu'])}</pre></div>
<div class="c"><div class="r">4 · o cliente recebeu</div><pre>{html.escape(t['cliente_recebeu'])}</pre></div>
</div><p class="sub">{t['protegidos']} dados pessoais protegidos neste turno.</p>"""
                      for i, t in enumerate(resumo["turnos"], 1))
    ok = not resumo["dados_que_chegaram_ao_provedor"]
    selo = ("<p class='ok'>✔ Nenhum dado pessoal chegou ao provedor.</p>" if ok else
            f"<p class='ruim'>✘ Chegaram ao provedor: {html.escape(', '.join(resumo['dados_que_chegaram_ao_provedor']))}</p>")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>lgpd-guard · demo do proxy</title><style>
:root{{--fundo:#f7f7f8;--cartao:#fff;--texto:#1d1d22;--suave:#5c5c66;--borda:#e3e3e8;--prov:#eef1ff}}
@media (prefers-color-scheme:dark){{:root{{--fundo:#141418;--cartao:#1d1d23;--texto:#ececf1;--suave:#a0a0ab;--borda:#2e2e37;--prov:#23263a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--fundo);color:var(--texto);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:32px 16px 64px}}h1{{font-size:28px;margin:0 0 4px}}h2{{font-size:19px;margin:32px 0 10px}}
.sub{{color:var(--suave)}}.grade{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}}
.c{{background:var(--cartao);border:1px solid var(--borda);border-radius:12px;padding:12px}}.c.prov{{background:var(--prov)}}
.r{{font-size:12px;color:var(--suave);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}}
pre{{white-space:pre-wrap;word-break:break-word;margin:0;font:14px/1.5 ui-monospace,Consolas,monospace}}
mark{{background:#ffe08a;color:#1d1d22;border-radius:4px;padding:0 3px}}.ok{{color:#2f9e6e;font-weight:700;font-size:18px}}
.ruim{{color:#d9485f;font-weight:700;font-size:18px}}a{{color:#4c5fd5}}
</style></head><body><main><h1>lgpd-guard · o proxy com um LLM de verdade</h1>
<p class="sub">Conversa de dois turnos passando pelo proxy até o modelo <b>{html.escape(resumo['modelo'])}</b> (aberto, via Ollama,
rodando no GitHub Actions). As colunas azuis mostram o que o provedor de IA viu.</p>{selo}{blocos}
<p class="sub"><a href="index.html">← benchmark de detecção</a> · <a href="https://github.com/arthurpenedo/lgpd-guard">código</a></p>
</main></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
