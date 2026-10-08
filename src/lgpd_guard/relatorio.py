"""Relatório HTML do benchmark (um arquivo, sem dependências)."""

from __future__ import annotations

import html
from datetime import date

from .entidades import TIPOS

_CSS = """
:root{--fundo:#f7f7f8;--cartao:#fff;--texto:#1d1d22;--suave:#5c5c66;--borda:#e3e3e8;
--a:#2f6fd6;--b:#2f9e6e;--c:#9a9aa6;--destaque:#4c5fd5;--ruim:#d9485f}
@media (prefers-color-scheme:dark){:root{--fundo:#141418;--cartao:#1d1d23;--texto:#ececf1;
--suave:#a0a0ab;--borda:#2e2e37;--c:#6b6b78}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);
font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 12px}.sub{color:var(--suave);margin:0 0 20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.card{background:var(--cartao);border:1px solid var(--borda);border-radius:12px;padding:16px}
.card .rot{color:var(--suave);font-size:13px}.card .num{font-size:30px;font-weight:700}
.card .det{font-size:13px;color:var(--suave)}
table{width:100%;border-collapse:collapse;background:var(--cartao);border:1px solid var(--borda);
border-radius:12px;overflow:hidden}th,td{padding:8px 12px;border-bottom:1px solid var(--borda);text-align:left}
th{font-size:13px;color:var(--suave);font-weight:600}td.n{font-variant-numeric:tabular-nums}
.barra{display:flex;align-items:center;gap:8px}.barra span.b{height:9px;border-radius:5px;display:inline-block}
.zero{color:var(--ruim);font-weight:600}pre{white-space:pre-wrap;background:var(--cartao);border:1px solid var(--borda);
border-radius:10px;padding:12px;font-size:14px}mark{background:#ffe08a;color:#1d1d22;border-radius:4px;padding:0 3px}
.leg{display:flex;gap:16px;font-size:13px;color:var(--suave);margin:8px 0}.leg i{display:inline-block;width:10px;
height:10px;border-radius:3px;margin-right:6px}footer{margin-top:48px;color:var(--suave);font-size:13px}a{color:var(--destaque)}
"""
_CORES = ["var(--a)", "var(--b)", "var(--c)", "var(--destaque)"]


def _barra(valor: float, cor: str) -> str:
    classe = " class='zero'" if valor == 0 else ""
    return (f"<div class='barra'><span class='b' style='width:{max(2, round(valor * 110))}px;background:{cor}'></span>"
            f"<span{classe}>{valor:.2f}</span></div>")


def gerar(resultados: dict[str, dict[str, dict]], exemplo: tuple[str, str] | None = None) -> str:
    """resultados = {conjunto: {sistema: avaliacao.to_dict()}}; exemplo = (texto original, anonimizado)."""
    secoes = []
    for conjunto, sistemas in resultados.items():
        nomes = list(sistemas)
        cards = "".join(
            f"<div class='card'><div class='rot'>{html.escape(n)}</div>"
            f"<div class='num' style='color:{_CORES[i % len(_CORES)]}'>F1 {s['geral']['f1']:.2f}</div>"
            f"<div class='det'>precisão {s['geral']['precisao']:.2f} · cobertura {s['geral']['cobertura']:.2f}<br>"
            f"dados protegidos (qualquer tipo): {s['protecao']['cobertura']:.0%}<br>"
            f"alarmes em textos sem dado pessoal: {s['falsos_alarmes_em_textos_limpos']} · {s['ms_por_texto']:.1f} ms/texto</div></div>"
            for i, (n, s) in enumerate(sistemas.items())
        )
        legenda = "".join(f"<span><i style='background:{_CORES[i % len(_CORES)]}'></i>{html.escape(n)}</span>"
                          for i, n in enumerate(nomes))
        tipos = [t for t in TIPOS if any(t in s["por_tipo"] for s in sistemas.values())]
        linhas = "".join(
            f"<tr><td>{t}</td><td class='n'>{next(iter(sistemas.values()))['por_tipo'].get(t, {}).get('vp', 0) + next(iter(sistemas.values()))['por_tipo'].get(t, {}).get('fn', 0)}</td>"
            + "".join(f"<td>{_barra(sistemas[n]['por_tipo'].get(t, {}).get('f1', 0.0), _CORES[i % len(_CORES)])}</td>"
                      for i, n in enumerate(nomes)) + "</tr>"
            for t in tipos
        )
        cab = "".join(f"<th>{html.escape(n)}</th>" for n in nomes)
        secoes.append(f"<h2>{html.escape(conjunto)}</h2><div class='cards'>{cards}</div>"
                      f"<div class='leg'>{legenda}</div><table><tr><th>Tipo</th><th>Qtd.</th>{cab}</tr>{linhas}</table>")

    bloco_exemplo = ""
    if exemplo:
        original, anonimizado = exemplo
        marcado = html.escape(anonimizado)
        import re

        marcado = re.sub(r"&lt;([A-Z_]+_\d+)&gt;", r"<mark>&lt;\1&gt;</mark>", marcado)
        bloco_exemplo = (f"<h2>Antes e depois</h2><p class='sub'>O que a empresa tem e o que o provedor do LLM recebe.</p>"
                         f"<pre>{html.escape(original)}</pre><pre>{marcado}</pre>")

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>lgpd-guard · benchmark</title>
<style>{_CSS}</style></head><body><main>
<h1>lgpd-guard · benchmark de detecção de dados pessoais</h1>
<p class="sub">F1 por tipo de dado, em conjuntos 100% sintéticos de mensagens de atendimento bancário · gerado em
{date.today():%d/%m/%Y}. Valores em vermelho: o sistema não detecta aquele tipo.
<a href="demo.html">Veja o proxy funcionando com um LLM de verdade →</a></p>
{bloco_exemplo}
{''.join(secoes)}
<h2>Como ler</h2>
<p><b>Desenvolvimento:</b> as regras foram ajustadas olhando os erros deste conjunto, então o número é otimista.
<b>Desafio:</b> escrito depois, com frases e formatos novos, e nunca usado para ajuste: mede a generalização.
<b>Dados protegidos</b> conta qualquer detecção que cubra o dado, mesmo com o tipo errado, porque para anonimizar
o que importa é o dado não sair. O Presidio não tem reconhecedores brasileiros (CPF, CNPJ, RG, CEP...), por isso
esses tipos aparecem zerados nele.</p>
<footer>Gerado pelo <a href="https://github.com/arthurpenedo/lgpd-guard">lgpd-guard</a> · dados 100% fictícios.</footer>
</main></body></html>"""
