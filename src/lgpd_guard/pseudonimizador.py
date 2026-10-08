"""Pseudonimização reversível: troca cada dado por um marcador antes do LLM e desfaz depois.

    "Meu CPF é 529.982.247-25"  ->  "Meu CPF é <CPF_1>"  ->  (LLM)  ->  "Seu CPF <CPF_1> está ok"
                                                                      ->  "Seu CPF 529.982.247-25 está ok"

O mesmo valor recebe sempre o mesmo marcador dentro de um cofre (sessão), então o
LLM continua entendendo que "o CPF do começo" e "o CPF do fim" são o mesmo. O cofre
fica do lado da empresa; o provedor do LLM só vê marcadores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .detector import Detector
from .entidades import Entidade
from .validadores import digitos

_MARCADOR = re.compile(r"<([A-Z_]+)_(\d+)>")


def _chave(entidade: Entidade) -> str:
    """Forma canônica do valor, para '529.982.247-25' e '52998224725' virarem o mesmo marcador."""
    if entidade.tipo in {"CPF", "CNPJ", "CARTAO", "TELEFONE", "CEP", "RG", "CONTA_BANCARIA"}:
        return f"{entidade.tipo}:{digitos(entidade.texto)}"
    return f"{entidade.tipo}:{' '.join(entidade.texto.lower().split())}"


@dataclass
class Cofre:
    """Guarda a correspondência marcador <-> valor original de uma sessão."""

    por_chave: dict[str, str] = field(default_factory=dict)
    por_marcador: dict[str, str] = field(default_factory=dict)
    contadores: dict[str, int] = field(default_factory=dict)

    def marcador_para(self, entidade: Entidade) -> str:
        chave = _chave(entidade)
        if chave not in self.por_chave:
            n = self.contadores.get(entidade.tipo, 0) + 1
            self.contadores[entidade.tipo] = n
            marcador = f"<{entidade.tipo}_{n}>"
            self.por_chave[chave] = marcador
            self.por_marcador[marcador] = entidade.texto
        return self.por_chave[chave]

    def __len__(self) -> int:
        return len(self.por_marcador)


@dataclass
class Resultado:
    texto: str
    entidades: list[Entidade]
    cofre: Cofre


class Pseudonimizador:
    def __init__(self, detector: Detector | None = None) -> None:
        self.detector = detector or Detector()

    def anonimizar(self, texto: str, cofre: Cofre | None = None) -> Resultado:
        cofre = cofre if cofre is not None else Cofre()
        entidades = self.detector.detectar(texto)
        partes, cursor = [], 0
        for e in entidades:
            partes.append(texto[cursor:e.inicio])
            partes.append(cofre.marcador_para(e))
            cursor = e.fim
        partes.append(texto[cursor:])
        return Resultado("".join(partes), entidades, cofre)

    @staticmethod
    def restaurar(texto: str, cofre: Cofre) -> str:
        """Desfaz a troca. Marcadores que o LLM inventou (não estão no cofre) ficam como estão."""
        return _MARCADOR.sub(lambda m: cofre.por_marcador.get(m.group(0), m.group(0)), texto)

    def mascarar(self, texto: str) -> str:
        """Versão irreversível para logs: mantém só o tipo e os 2 últimos caracteres."""
        partes, cursor = [], 0
        for e in self.detector.detectar(texto):
            partes.append(texto[cursor:e.inicio])
            partes.append(f"[{e.tipo} ***{e.texto[-2:]}]" if e.tipo not in {"NOME", "ENDERECO", "EMAIL"} else f"[{e.tipo}]")
            cursor = e.fim
        partes.append(texto[cursor:])
        return "".join(partes)
