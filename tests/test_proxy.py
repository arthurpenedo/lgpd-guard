import json
import re

import httpx
from fastapi.testclient import TestClient

from lgpd_guard.proxy import INSTRUCAO_MARCADORES, criar_app

CPF = "529.982.247-25"
CARTAO = "4111 1111 1111 1111"


class ProvedorFalso:
    """Simula o provedor de LLM: grava o que recebeu e responde citando os marcadores."""

    def __init__(self, status: int = 200) -> None:
        self.recebido: list[dict] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content)
        self.recebido.append({"corpo": corpo, "auth": request.headers.get("authorization")})
        if self.status != 200:
            return httpx.Response(self.status, text="limite de uso")
        ultima = corpo["messages"][-1]["content"]
        if isinstance(ultima, list):  # formato em partes
            ultima = " ".join(p.get("text", "") for p in ultima if isinstance(p, dict))
        marcadores = re.findall(r"<[A-Z_]+_\d+>", ultima)
        resposta = f"Certo, {' e '.join(marcadores) or 'sem marcadores'}. Bloqueei o cartão."
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "model": corpo.get("model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": resposta}, "finish_reason": "stop"}],
        })


def cliente(provedor: ProvedorFalso) -> TestClient:
    app = criar_app(upstream="http://provedor/v1", usar_ner=False, transporte=httpx.MockTransport(provedor))
    return TestClient(app)


def conversar(c: TestClient, texto: str, sessao: str | None = None, historico: list | None = None):
    mensagens = (historico or []) + [{"role": "user", "content": texto}]
    cab = {"Authorization": "Bearer chave-do-provedor", **({"X-Sessao": sessao} if sessao else {})}
    return c.post("/v1/chat/completions", json={"model": "qwen2.5:1.5b", "messages": mensagens}, headers=cab)


def test_provedor_nunca_ve_o_dado_e_cliente_recebe_restaurado():
    provedor = ProvedorFalso()
    r = conversar(cliente(provedor), f"Meu CPF é {CPF} e meu cartão {CARTAO} foi clonado.")
    assert r.status_code == 200
    enviado = json.dumps(provedor.recebido[0]["corpo"], ensure_ascii=False)
    assert CPF not in enviado and CARTAO not in enviado and "<CPF_1>" in enviado
    resposta = r.json()["choices"][0]["message"]["content"]
    assert CPF in resposta and CARTAO in resposta and "<CPF_1>" not in resposta
    assert r.headers["X-Dados-Protegidos"] == "2"


def test_instrucao_sobre_marcadores_so_quando_ha_dado():
    provedor = ProvedorFalso()
    c = cliente(provedor)
    conversar(c, "Qual o horário da agência?")
    conversar(c, f"Meu CPF é {CPF}")
    assert provedor.recebido[0]["corpo"]["messages"][0]["content"] != INSTRUCAO_MARCADORES
    assert provedor.recebido[1]["corpo"]["messages"][0]["content"] == INSTRUCAO_MARCADORES


def test_mesma_sessao_mantem_os_marcadores_entre_turnos():
    provedor = ProvedorFalso()
    c = cliente(provedor)
    r1 = conversar(c, f"Meu CPF é {CPF}")
    sessao = r1.headers["X-Sessao"]
    historico = [{"role": "user", "content": f"Meu CPF é {CPF}"}, r1.json()["choices"][0]["message"]]
    conversar(c, "E o CPF 52998224725 tem pendências?", sessao, historico)
    segundo = json.dumps(provedor.recebido[1]["corpo"], ensure_ascii=False)
    assert "<CPF_2>" not in segundo and segundo.count("<CPF_1>") >= 3  # histórico (2x) + pergunta nova


def test_chave_do_provedor_e_repassada_e_auditoria_sem_valores():
    provedor = ProvedorFalso()
    c = cliente(provedor)
    conversar(c, f"CPF {CPF}")
    assert provedor.recebido[0]["auth"] == "Bearer chave-do-provedor"
    auditoria = c.get("/auditoria").json()
    assert auditoria[-1]["protegidos"] == {"CPF": 1}
    assert CPF not in json.dumps(auditoria)


def test_conteudo_em_partes_formato_multimodal():
    provedor = ProvedorFalso()
    c = cliente(provedor)
    c.post("/v1/chat/completions", json={"model": "m", "messages": [
        {"role": "user", "content": [{"type": "text", "text": f"CPF {CPF}"}, {"type": "image_url", "image_url": {"url": "x"}}]},
    ]})
    partes = provedor.recebido[0]["corpo"]["messages"][-1]["content"]
    assert partes[0]["text"] == "CPF <CPF_1>" and partes[1]["type"] == "image_url"


def test_erros_e_validacoes():
    c = cliente(ProvedorFalso(status=429))
    assert conversar(c, f"CPF {CPF}").status_code == 429
    c = cliente(ProvedorFalso())
    assert c.post("/v1/chat/completions", json={"model": "m", "messages": [], "stream": True}).status_code == 400
    assert c.post("/v1/chat/completions", json={"model": "m"}).status_code == 400
    assert c.get("/saude").json()["status"] == "ok"
