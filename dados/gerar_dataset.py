"""Gera o conjunto de teste rotulado (dados/teste.jsonl), 100% sintético.

Cada texto imita uma mensagem de atendimento bancário (chat, e-mail, transcrição de
ligação, formulário) e traz as posições exatas de cada dado pessoal. Inclui casos
difíceis de propósito:
- formatos variados (CPF com e sem pontuação, telefone com +55, cartão sem espaços);
- nomes em minúsculas, como numa transcrição automática de ligação;
- "falsos amigos" que NÃO são dados pessoais: protocolos de 11 dígitos, valores em
  reais, datas de vencimento, números de pedido, nomes de bancos e de cidades.

Uso: python dados/gerar_dataset.py  (semente fixa: o arquivo é sempre o mesmo)
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path

from faker import Faker

SEMENTE = 2026
N_TEXTOS = 300

fake = Faker("pt_BR")
Faker.seed(SEMENTE)
rnd = random.Random(SEMENTE)

DDDS = ["11", "21", "31", "41", "51", "61", "71", "81", "19", "48", "85", "62"]


# ------------------------------------------------------------------ valores
def cpf() -> str:
    valor = fake.cpf()  # válido e formatado
    return valor if rnd.random() < 0.7 else valor.replace(".", "").replace("-", "")


def cnpj() -> str:
    valor = fake.cnpj()
    return valor if rnd.random() < 0.8 else "".join(c for c in valor if c.isdigit())


def telefone() -> str:
    ddd, num = rnd.choice(DDDS), f"9{rnd.randint(1000, 9999)}{rnd.randint(1000, 9999)}"
    return rnd.choice([
        f"({ddd}) {num[:5]}-{num[5:]}", f"{ddd} {num[:5]}-{num[5:]}", f"+55 {ddd} {num[:5]}-{num[5:]}",
        f"{ddd}{num}", f"({ddd}){num}",
    ])


def cartao() -> str:
    numero = fake.credit_card_number(card_type=rnd.choice(["visa16", "mastercard"]))
    return " ".join(numero[i:i + 4] for i in range(0, 16, 4)) if rnd.random() < 0.6 else numero


def cep() -> str:
    return fake.postcode(formatted=True)


def rg() -> str:
    n = f"{rnd.randint(10, 59)}{rnd.randint(100, 999)}{rnd.randint(100, 999)}"
    return f"{n[:2]}.{n[2:5]}.{n[5:]}-{rnd.choice('0123456789X')}"


def placa() -> str:
    letras = "".join(rnd.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    return f"{letras}{rnd.randint(0, 9)}{rnd.choice('ABCDEFGHIJ')}{rnd.randint(10, 99)}" if rnd.random() < 0.6 \
        else f"{letras}-{rnd.randint(1000, 9999)}"


def nascimento() -> str:
    return fake.date_of_birth(minimum_age=18, maximum_age=85).strftime("%d/%m/%Y")


def conta() -> str:
    return f"{rnd.randint(1000, 9999)}-{rnd.randint(0, 9)} conta {rnd.randint(10000, 999999)}-{rnd.randint(0, 9)}"


def endereco() -> str:
    tipo = rnd.choice(["Rua", "Avenida", "Av.", "Travessa", "Alameda"])
    rua = fake.street_name().split(" ", 1)[-1]
    sufixo = rnd.choice(["", f" - apto {rnd.randint(11, 304)}", f", casa {rnd.randint(1, 9)}"])
    return f"{tipo} {rua}, {fake.building_number()}{sufixo}"


def nome(minusculo: bool = False) -> str:
    valor = rnd.choice([fake.name, lambda: f"{fake.first_name()} {fake.last_name()}"])()
    for prefixo in ("Sr. ", "Sra. ", "Dr. ", "Dra. ", "Srta. "):
        valor = valor.removeprefix(prefixo)
    return valor.lower() if minusculo else valor


# ------------------------------------------------------------------ falsos amigos (não são PII)
def protocolo() -> str:
    while True:  # 11 dígitos que NÃO formam um CPF válido
        n = "".join(str(rnd.randint(0, 9)) for _ in range(11))
        from lgpd_guard.validadores import cpf_valido  # import tardio: o gerador também roda sem instalar

        if not cpf_valido(n):
            return n


def valor() -> str:
    return f"R$ {rnd.randint(10, 9999):,}".replace(",", ".") + f",{rnd.randint(0, 99):02d}"


def vencimento() -> str:
    return fake.date_between(start_date="-30d", end_date="+60d").strftime("%d/%m/%Y")


BANCOS = ["Banco do Brasil", "Caixa", "Itaú", "Bradesco", "Santander", "Nubank", "Banco Inter"]


# ------------------------------------------------------------------ montagem com posições
class Texto:
    def __init__(self) -> None:
        self.partes: list[str] = []
        self.entidades: list[list] = []
        self.tamanho = 0

    def t(self, texto: str) -> "Texto":
        self.partes.append(texto)
        self.tamanho += len(texto)
        return self

    def p(self, tipo: str, valor_: str) -> "Texto":
        self.entidades.append([self.tamanho, self.tamanho + len(valor_), tipo])
        return self.t(valor_)

    def fechar(self) -> tuple[str, list]:
        return "".join(self.partes), self.entidades


def modelos() -> list:
    """Cada função monta um texto; a variedade de estruturas é o que importa."""
    return [
        lambda: Texto().t("Olá, meu nome é ").p("NOME", nome()).t(" e meu CPF é ").p("CPF", cpf())
        .t(". Não reconheço uma compra de ").t(valor()).t(" no meu cartão.").fechar(),

        lambda: Texto().t("Bom dia! Sou a ").p("NOME", nome()).t(", cliente há anos. Podem me ligar no ")
        .p("TELEFONE", telefone()).t("? O protocolo do meu chamado é ").t(protocolo()).t(".").fechar(),

        lambda: Texto().t("Prezados, solicito a segunda via do boleto com vencimento em ").t(vencimento())
        .t(". Meus dados: e-mail ").p("EMAIL", fake.email()).t(", CPF ").p("CPF", cpf()).t(". Atenciosamente, ")
        .p("NOME", nome()).fechar(),

        lambda: Texto().t("[transcrição] atendente: pode confirmar seu nome completo? cliente: ")
        .p("NOME", nome(minusculo=True)).t(". atendente: e o cpf? cliente: ").p("CPF", cpf()).fechar(),

        lambda: Texto().t("Quero cancelar o cartão final ").t(str(rnd.randint(1000, 9999)))
        .t(". O número completo é ").p("CARTAO", cartao()).t(" e o titular é ").p("NOME", nome()).t(".").fechar(),

        lambda: Texto().t("Atualização cadastral\nNome: ").p("NOME", nome()).t("\nCPF: ").p("CPF", cpf())
        .t("\nData de nascimento: ").p("DATA_NASCIMENTO", nascimento()).t("\nEndereço: ").p("ENDERECO", endereco())
        .t("\nCEP: ").p("CEP", cep()).t("\nCelular: ").p("TELEFONE", telefone()).fechar(),

        lambda: Texto().t("Fiz um Pix de ").t(valor()).t(" para a chave aleatória ").p("PIX_ALEATORIA", str(uuid.UUID(int=rnd.getrandbits(128))))
        .t(" e o dinheiro não chegou. Foi pelo ").t(rnd.choice(BANCOS)).t(".").fechar(),

        lambda: Texto().t("A empresa ").t(fake.company()).t(", CNPJ ").p("CNPJ", cnpj())
        .t(", quer abrir conta PJ. O responsável é ").p("NOME", nome()).t(", RG ").p("RG", rg()).t(".").fechar(),

        lambda: Texto().t("Sofri um acidente com o carro placa ").p("PLACA", placa())
        .t(" e preciso acionar o seguro. Meu telefone: ").p("TELEFONE", telefone()).t(".").fechar(),

        lambda: Texto().t("Por favor depositem o reembolso na agência ").p("CONTA_BANCARIA", conta())
        .t(" em nome de ").p("NOME", nome()).t(".").fechar(),

        lambda: Texto().t("Meu pai, ").p("NOME", nome()).t(", nasceu em ").p("DATA_NASCIMENTO", nascimento())
        .t(" e quer fazer um empréstimo consignado. Ele mora em ").t(fake.city()).t(".").fechar(),

        lambda: Texto().t("Recebi uma ligação de alguém do ").t(rnd.choice(BANCOS))
        .t(" pedindo meu código de segurança. O número que ligou foi ").p("TELEFONE", telefone()).t(". É golpe?").fechar(),

        # textos SEM dado pessoal (medem falsos positivos)
        lambda: Texto().t("Qual a taxa do cheque especial? Vi ").t(valor()).t(" de juros na fatura que vence em ")
        .t(vencimento()).t(". O protocolo é ").t(protocolo()).t(".").fechar(),

        lambda: Texto().t("O pedido #").t(str(rnd.randint(100000, 999999))).t(" foi entregue em ").t(fake.city())
        .t(", mas cobraram ").t(valor()).t(" de frete. Comprei pelo app do ").t(rnd.choice(BANCOS)).t(".").fechar(),

        lambda: Texto().t("Vocês têm agência em ").t(fake.city()).t("? Preciso falar com o gerente sobre investimentos ")
        .t("acima de ").t(valor()).t(".").fechar(),

        lambda: Texto().t("cliente: oi bom dia eu queria saber do meu extrato. atendente: claro, vou te ajudar. ")
        .t("cliente: tem uma cobrança de ").t(valor()).t(" que eu não fiz").fechar(),
    ]


def main() -> None:
    destino = Path(__file__).with_name("teste.jsonl")
    geradores = modelos()
    with destino.open("w", encoding="utf-8") as f:
        for i in range(N_TEXTOS):
            texto, entidades = geradores[i % len(geradores)]()
            for inicio, fim, _ in entidades:  # sanidade: as posições batem com o texto
                assert texto[inicio:fim].strip() == texto[inicio:fim]
            f.write(json.dumps({"id": f"t{i:03d}", "texto": texto, "entidades": entidades}, ensure_ascii=False) + "\n")
    print(f"{N_TEXTOS} textos salvos em {destino}")


if __name__ == "__main__":
    main()
