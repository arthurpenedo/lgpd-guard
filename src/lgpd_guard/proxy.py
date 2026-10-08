"""Proxy compatível com a API de chat da OpenAI: o dado pessoal não sai da empresa.

    aplicação ──► lgpd-guard (proxy) ──► provedor de LLM (OpenAI, Ollama, vLLM...)
                  anonimiza na ida,
                  restaura na volta

A aplicação só troca a URL base. Cada conversa tem um cofre (cabeçalho X-Sessao), então
o mesmo CPF vira o mesmo marcador em todos os turnos e a resposta é restaurada corretamente.
O registro de auditoria guarda QUAIS tipos foram protegidos, nunca os valores.

Configuração por variáveis de ambiente:
    LGPD_GUARD_UPSTREAM   URL base do provedor (padrão: http://localhost:11434/v1, o Ollama)
    LGPD_GUARD_SEM_NER    "1" para usar só as regras (sem spaCy)
"""

from __future__ import annotations

import copy
import os
import time
import uuid
from collections import Counter, OrderedDict
from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from . import __version__
from .detector import Detector
from .pseudonimizador import Cofre, Pseudonimizador

INSTRUCAO_MARCADORES = (
    "Algumas informações desta conversa foram substituídas por marcadores entre sinais de menor e maior, "
    "como <NOME_1> ou <CPF_1>. Trate cada marcador como se fosse o dado real e, quando precisar mencioná-lo, "
    "repita o marcador exatamente como está, sem alterar, traduzir ou explicar."
)


@dataclass
class Sessoes:
    """Cofres por conversa, com limite de tamanho e expiração (memória da instância)."""

    maximo: int = 10_000
    ttl_segundos: int = 3600
    _dados: OrderedDict = field(default_factory=OrderedDict)

    def cofre(self, sessao: str) -> Cofre:
        agora = time.time()
        for chave in [k for k, (_, t) in self._dados.items() if agora - t > self.ttl_segundos]:
            del self._dados[chave]
        cofre, _ = self._dados.pop(sessao, (Cofre(), agora))
        self._dados[sessao] = (cofre, agora)
        while len(self._dados) > self.maximo:
            self._dados.popitem(last=False)
        return cofre


def _anonimizar_conteudo(conteudo, p: Pseudonimizador, cofre: Cofre, tipos: Counter):
    """O 'content' pode ser texto ou uma lista de partes (formato multimodal da OpenAI)."""
    if isinstance(conteudo, str):
        r = p.anonimizar(conteudo, cofre)
        tipos.update(e.tipo for e in r.entidades)
        return r.texto
    if isinstance(conteudo, list):
        novas = []
        for parte in conteudo:
            if isinstance(parte, dict) and parte.get("type") == "text" and isinstance(parte.get("text"), str):
                parte = {**parte, "text": _anonimizar_conteudo(parte["text"], p, cofre, tipos)}
            novas.append(parte)
        return novas
    return conteudo


def criar_app(upstream: str | None = None, usar_ner: bool | None = None,
              transporte: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    upstream = (upstream or os.environ.get("LGPD_GUARD_UPSTREAM", "http://localhost:11434/v1")).rstrip("/")
    if usar_ner is None:
        usar_ner = os.environ.get("LGPD_GUARD_SEM_NER") != "1"
    pseudo = Pseudonimizador(Detector(usar_ner=usar_ner))
    sessoes = Sessoes()
    auditoria: list[dict] = []
    app = FastAPI(title="lgpd-guard proxy", version=__version__)
    app.state.auditoria = auditoria

    @app.get("/saude")
    async def saude() -> dict:
        return {"status": "ok", "upstream": upstream, "ner": pseudo.detector.ner_ativo}

    @app.get("/auditoria")
    async def ver_auditoria(limite: int = 50) -> list[dict]:
        return auditoria[-limite:]

    @app.post("/v1/chat/completions")
    async def chat(request: Request, x_sessao: str | None = Header(default=None),
                   authorization: str | None = Header(default=None)) -> JSONResponse:
        corpo = await request.json()
        if corpo.get("stream"):
            raise HTTPException(400, "streaming ainda não é suportado pelo lgpd-guard; envie stream=false")
        mensagens = corpo.get("messages")
        if not isinstance(mensagens, list):
            raise HTTPException(400, "campo 'messages' ausente ou inválido")

        sessao = x_sessao or uuid.uuid4().hex
        cofre = sessoes.cofre(sessao)
        tipos: Counter = Counter()
        saida = copy.deepcopy(corpo)
        saida["messages"] = [
            {**m, "content": _anonimizar_conteudo(m.get("content"), pseudo, cofre, tipos)} for m in mensagens
        ]
        if tipos or len(cofre):
            saida["messages"].insert(0, {"role": "system", "content": INSTRUCAO_MARCADORES})

        cabecalhos = {"Content-Type": "application/json"}
        if authorization:
            cabecalhos["Authorization"] = authorization  # a chave do provedor só é repassada
        async with httpx.AsyncClient(transport=transporte, timeout=120) as cliente:
            try:
                resp = await cliente.post(f"{upstream}/chat/completions", json=saida, headers=cabecalhos)
            except httpx.HTTPError as erro:
                raise HTTPException(502, f"provedor indisponível: {erro.__class__.__name__}") from erro
        if resp.status_code >= 400:
            return JSONResponse(status_code=resp.status_code, content={"erro_do_provedor": resp.text[:500]})

        dados = resp.json()
        for escolha in dados.get("choices", []):
            msg = escolha.get("message") or {}
            if isinstance(msg.get("content"), str):
                msg["content"] = pseudo.restaurar(msg["content"], cofre)

        auditoria.append({
            "quando": time.strftime("%Y-%m-%dT%H:%M:%S"), "sessao": sessao[:8],
            "protegidos": dict(tipos), "total": sum(tipos.values()), "modelo": corpo.get("model"),
        })
        del auditoria[:-1000]
        return JSONResponse(content=dados, headers={"X-Sessao": sessao, "X-Dados-Protegidos": str(sum(tipos.values()))})

    return app

