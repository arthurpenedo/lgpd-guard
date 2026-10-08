"""Tipos de dado pessoal cobertos e a representação de uma detecção."""

from __future__ import annotations

from dataclasses import asdict, dataclass

# tipo -> descrição (todos são dados pessoais ou permitem identificar alguém, pela LGPD)
TIPOS = {
    "CPF": "CPF (com dígitos verificadores válidos)",
    "CNPJ": "CNPJ (com dígitos verificadores válidos)",
    "RG": "RG (exige contexto, como 'RG' ou 'identidade')",
    "CARTAO": "Número de cartão (algoritmo de Luhn)",
    "TELEFONE": "Telefone fixo ou celular, com ou sem DDD/+55",
    "EMAIL": "Endereço de e-mail",
    "CEP": "CEP",
    "PIX_ALEATORIA": "Chave Pix aleatória (UUID)",
    "PLACA": "Placa de veículo (padrão antigo e Mercosul)",
    "CONTA_BANCARIA": "Agência e conta bancária (exige contexto)",
    "DATA_NASCIMENTO": "Data de nascimento (exige contexto)",
    "ENDERECO": "Endereço (logradouro e número)",
    "NOME": "Nome de pessoa",
}


@dataclass(frozen=True, order=True)
class Entidade:
    """Um trecho do texto identificado como dado pessoal."""

    inicio: int
    fim: int
    tipo: str
    texto: str
    confianca: float = 1.0
    fonte: str = "regra"  # regra, regra+validador, regra+contexto, ner

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise ValueError(f"tipo desconhecido: {self.tipo}")
        if not 0 <= self.inicio < self.fim:
            raise ValueError("posições inválidas")

    def sobrepoe(self, outra: Entidade) -> bool:
        return self.inicio < outra.fim and outra.inicio < self.fim

    def to_dict(self) -> dict:
        return asdict(self)
