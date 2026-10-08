"""Conjunto de DESAFIO (dados/desafio.jsonl): frases e formatos que as regras nunca viram.

As regras do lgpd-guard foram ajustadas olhando os erros do conjunto de desenvolvimento
(teste.jsonl). Este conjunto foi escrito DEPOIS, com outros modelos de frase, e não é
usado para ajustar nada: mede o quanto o detector generaliza. Ele reaproveita só os
geradores de valores (CPF, telefone...) do outro script, nunca as frases.
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path

import gerar_dataset as g
from faker import Faker

SEMENTE = 777
N_TEXTOS = 160

g.fake = Faker("pt_BR")
Faker.seed(SEMENTE)
g.rnd = random.Random(SEMENTE)
rnd = g.rnd
Texto = g.Texto


def cpf_com_espacos() -> str:
    d = "".join(c for c in g.fake.cpf() if c.isdigit())
    return f"{d[:3]} {d[3:6]} {d[6:9]} {d[9:]}"


def telefone_com_zero() -> str:
    num = f"9{rnd.randint(1000, 9999)}{rnd.randint(1000, 9999)}"
    return f"(0{rnd.choice(g.DDDS)}) {num[:5]}-{num[5:]}"


def cartao_com_hifens() -> str:
    numero = g.fake.credit_card_number(card_type="visa16")
    return "-".join(numero[i:i + 4] for i in range(0, 16, 4))


def email_maiusculo() -> str:
    return g.fake.email().upper()


def modelos() -> list:
    return [
        # WhatsApp, sem pontuação, nome no fim
        lambda: Texto().t("oii tudo bem? to sem acesso ao app, meu cpf ").p("CPF", g.cpf())
        .t(" pode ver pra mim? obg, ").p("NOME", g.nome()).fechar(),

        # nome no começo, como assinatura invertida
        lambda: Texto().p("NOME", g.nome()).t(" aqui. Troquei de número, o novo é ").p("TELEFONE", telefone_com_zero())
        .t(", favor atualizar.").fechar(),

        # CPF com espaços e e-mail em maiúsculas
        lambda: Texto().t("Segue CPF ").p("CPF", cpf_com_espacos()).t(" e email ").p("EMAIL", email_maiusculo())
        .t(" para envio do informe de rendimentos.").fechar(),

        # nome depois de "falei com" (atendente também é pessoa)
        lambda: Texto().t("Ontem falei com ").p("NOME", g.nome()).t(" na agência e ele disse que o estorno de ")
        .t(g.valor()).t(" sai em 5 dias úteis. Já passou!").fechar(),

        # endereço abreviado e CEP na mesma linha
        lambda: Texto().t("Mudei para ").p("ENDERECO", f"R. {g.fake.street_name().split(' ', 1)[-1]}, {g.fake.building_number()}")
        .t(" (CEP ").p("CEP", g.cep()).t("), mandem o cartão novo para lá.").fechar(),

        # cartão com hífens, em lista
        lambda: Texto().t("Dados para contestação:\n- cartão: ").p("CARTAO", cartao_com_hifens())
        .t("\n- valor: ").t(g.valor()).t("\n- data: ").t(g.vencimento()).fechar(),

        # várias pessoas na mesma mensagem
        lambda: Texto().t("A conta conjunta é minha e da ").p("NOME", g.nome()).t(". Quero incluir o ")
        .p("NOME", g.nome()).t(" como dependente.").fechar(),

        # Pix por e-mail e chave aleatória juntos
        lambda: Texto().t("Mandei o Pix pra chave ").p("EMAIL", g.fake.email()).t(" mas era pra ser na ")
        .p("PIX_ALEATORIA", str(uuid.UUID(int=rnd.getrandbits(128)))).t(". Dá pra estornar?").fechar(),

        # CNPJ sem pontuação no meio de frase longa
        lambda: Texto().t("Sou MEI, CNPJ ").p("CNPJ", "".join(c for c in g.fake.cnpj() if c.isdigit()))
        .t(", e quero saber se posso usar a maquininha de vocês no meu comércio em ").t(g.fake.city()).t(".").fechar(),

        # data de nascimento por extenso de contexto diferente
        lambda: Texto().t("Faço aniversário dia ").p("DATA_NASCIMENTO", g.nascimento())
        .t(" e queria saber se tem algum benefício no cartão.").fechar(),

        # sem dado pessoal, com números que parecem dados
        lambda: Texto().t("A fatura de ").t(g.valor()).t(" com vencimento ").t(g.vencimento())
        .t(" veio com código de barras 34191.79001 01043.510047 91020.150008 1 ").t(str(rnd.randint(10**9, 10**10)))
        .t(". Está certo?").fechar(),

        lambda: Texto().t("Quanto rende ").t(g.valor()).t(" no CDB de 110% do CDI por 12 meses? Vi no site do ")
        .t(rnd.choice(g.BANCOS)).t(".").fechar(),
    ]


def main() -> None:
    destino = Path(__file__).with_name("desafio.jsonl")
    geradores = modelos()
    with destino.open("w", encoding="utf-8") as f:
        for i in range(N_TEXTOS):
            texto, entidades = geradores[i % len(geradores)]()
            f.write(json.dumps({"id": f"d{i:03d}", "texto": texto, "entidades": entidades}, ensure_ascii=False) + "\n")
    print(f"{N_TEXTOS} textos salvos em {destino}")


if __name__ == "__main__":
    main()
