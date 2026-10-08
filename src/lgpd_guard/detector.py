"""Junta os reconhecedores e resolve sobreposições (o mesmo trecho não pode ter dois tipos)."""

from __future__ import annotations

from .entidades import TIPOS, Entidade
from .nomes import reconhecer_nomes, spacy_disponivel
from .reconhecedores import reconhecer

# Quando dois achados se sobrepõem, vence o de maior prioridade; empate, o mais longo.
# Identificadores validados matematicamente vêm primeiro: um CPF válido não é telefone.
_PRIORIDADE = {t: i for i, t in enumerate([
    "EMAIL", "PIX_ALEATORIA", "CNPJ", "CPF", "CARTAO", "CONTA_BANCARIA", "RG", "DATA_NASCIMENTO",
    "TELEFONE", "CEP", "PLACA", "ENDERECO", "NOME",
])}


class Detector:
    def __init__(self, tipos: list[str] | None = None, usar_ner: bool = True) -> None:
        desconhecidos = set(tipos or []) - set(TIPOS)
        if desconhecidos:
            raise ValueError(f"tipos desconhecidos: {', '.join(sorted(desconhecidos))}")
        self.tipos = set(tipos or TIPOS)
        self.usar_ner = usar_ner

    @property
    def ner_ativo(self) -> bool:
        return self.usar_ner and spacy_disponivel()

    def detectar(self, texto: str) -> list[Entidade]:
        candidatos = reconhecer(texto)
        if "NOME" in self.tipos:
            candidatos += reconhecer_nomes(texto, self.usar_ner)
        candidatos = [e for e in candidatos if e.tipo in self.tipos]
        candidatos.sort(key=lambda e: (_PRIORIDADE[e.tipo], -(e.fim - e.inicio), -e.confianca))
        escolhidos: list[Entidade] = []
        for e in candidatos:
            if not any(e.sobrepoe(x) for x in escolhidos):
                escolhidos.append(e)
        return sorted(escolhidos)
