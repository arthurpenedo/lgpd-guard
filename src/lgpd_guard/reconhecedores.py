"""Reconhecedores por regra: padrão + validador matemático + palavras de contexto.

Três níveis de confiança, do mais forte ao mais fraco:
- regra+validador: o formato bate E os dígitos verificadores conferem (CPF, CNPJ, cartão);
- regra: formato inequívoco por si só (e-mail, UUID de chave Pix, placa);
- regra+contexto: formato ambíguo, aceito só com uma palavra-chave por perto (RG, conta, nascimento).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from . import validadores as v
from .entidades import Entidade

# separador opcional entre blocos de dígitos: ponto, hífen, espaço ou barra
_S = r"[\s.\-/]?"


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


@dataclass(frozen=True)
class Reconhecedor:
    tipo: str
    padrao: re.Pattern
    validador: Callable[[str], bool] | None = None
    contexto: re.Pattern | None = None  # palavras que precisam aparecer perto
    contexto_obrigatorio: bool = False
    janela: int = 40
    confianca: float = 0.95
    grupo: int = 0

    def encontrar(self, texto: str, texto_norm: str) -> Iterator[Entidade]:
        for achado in self.padrao.finditer(texto):
            inicio, fim = achado.span(self.grupo)
            trecho = texto[inicio:fim]
            if self.validador and not self.validador(trecho):
                continue
            perto = texto_norm[max(0, inicio - self.janela):inicio]
            tem_contexto = bool(self.contexto and self.contexto.search(perto))
            if self.contexto_obrigatorio and not tem_contexto:
                continue
            fonte = "regra+validador" if self.validador else ("regra+contexto" if tem_contexto else "regra")
            confianca = min(1.0, self.confianca + (0.05 if tem_contexto else 0))
            yield Entidade(inicio, fim, self.tipo, trecho, round(confianca, 2), fonte)


def _telefone_valido(trecho: str) -> bool:
    d = v.digitos(trecho)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) in (10, 11):
        if not v.ddd_valido(d[:2]):
            return False
        if len(d) == 11 and d[2] != "9":  # celular com 9 dígitos começa com 9
            return False
        if "+" in trecho or "(" in trecho:  # +55 ou (DDD): é telefone, mesmo que os dígitos formem um CPF
            return True
        return not v.cpf_valido(d)  # 11 dígitos soltos que são um CPF válido ficam com o CPF
    return len(d) in (8, 9) and not trecho.strip().isdigit()  # sem DDD, só com separador (9999-9999)


def _cartao_valido(trecho: str) -> bool:
    # 15 (Amex), 16 (Visa, Master, Elo) ou 19 dígitos: impede que um telefone com +55
    # (13 dígitos) que passe no Luhn por acaso vire cartão
    return len(v.digitos(trecho)) in (15, 16, 19) and v.luhn_valido(trecho)


_CONTEXTO_TELEFONE = re.compile(r"tel|fone|celular|whats|zap|contato|ligar|ligue|\bliga\b|numero")

RECONHECEDORES: list[Reconhecedor] = [
    Reconhecedor("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), confianca=0.99),
    Reconhecedor("PIX_ALEATORIA", re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), confianca=0.95),
    Reconhecedor("CNPJ", re.compile(rf"(?<![\d.])\d{{2}}{_S}\d{{3}}{_S}\d{{3}}{_S}\d{{4}}{_S}\d{{2}}(?![\d])"),
                 validador=v.cnpj_valido, confianca=0.97),
    Reconhecedor("CPF", re.compile(rf"(?<![\d.])\d{{3}}{_S}\d{{3}}{_S}\d{{3}}{_S}\d{{2}}(?![\d])"),
                 validador=v.cpf_valido, contexto=re.compile(r"\bcpf\b"), confianca=0.95),
    Reconhecedor("CARTAO", re.compile(r"(?<![\d+])(?:\d[ \-.]?){12,18}\d(?!\d)"),
                 validador=_cartao_valido, contexto=re.compile(r"cartao|credito|debito|visa|master|elo\b"),
                 confianca=0.9),
    # telefone formatado: parênteses, hífen, espaço ou +55 deixam claro que é telefone
    Reconhecedor("TELEFONE", re.compile(
        r"(?<![\d\w])(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]?\d{4}(?![\d\w])"),
        validador=lambda s: _telefone_valido(s) and not s.isdigit(), contexto=_CONTEXTO_TELEFONE, confianca=0.85),
    # só dígitos: pode ser protocolo ou número de pedido, então exige contexto ("me liga no", "celular"...)
    Reconhecedor("TELEFONE", re.compile(r"(?<![\d\w])(?:55)?\d{10,11}(?![\d\w])"),
                 validador=_telefone_valido, contexto=_CONTEXTO_TELEFONE, contexto_obrigatorio=True, confianca=0.8),
    Reconhecedor("CEP", re.compile(r"(?<![\d.])\d{5}-\d{3}(?!\d)"),
                 contexto=re.compile(r"\bcep\b|endereco|rua|av\b|avenida"), confianca=0.85),
    Reconhecedor("CEP", re.compile(r"(?<![\d.])\d{8}(?!\d)"), contexto=re.compile(r"\bcep\b"),
                 contexto_obrigatorio=True, janela=15, confianca=0.85),
    Reconhecedor("PLACA", re.compile(r"\b[A-Z]{3}-?\d[A-Z0-9]\d{2}\b"), confianca=0.85),
    Reconhecedor("RG", re.compile(r"(?<![\d.])\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX](?![\d])"),
                 contexto=re.compile(r"\brg\b|identidade|registro geral"), contexto_obrigatorio=True, confianca=0.85),
    Reconhecedor("CONTA_BANCARIA", re.compile(
        r"(?:ag(?:encia|\.)?\s*:?\s*)?(\d{4}(?:-\d)?\s*(?:/|,|e)?\s*(?:c/?c|conta(?: corrente)?)?\s*:?\s*\d{4,12}-[\dxX])",
        re.IGNORECASE), contexto=re.compile(r"agencia|\bag\b|conta|\bc/?c\b|deposit|transfer"),
        contexto_obrigatorio=True, janela=50, confianca=0.85, grupo=1),
    Reconhecedor("DATA_NASCIMENTO", re.compile(r"\b\d{2}/\d{2}/(?:19|20)\d{2}\b"),
                 contexto=re.compile(r"nasc|nasceu|aniversario|idade"), contexto_obrigatorio=True,
                 janela=45, confianca=0.85),
    Reconhecedor("ENDERECO", re.compile(
        r"\b(?:Rua|R\.|Avenida|Av\.?|Travessa|Alameda|Al\.|Rodovia|Estrada|Praça|Largo)\s+(?:d[aeo]s?\s+)?"
        r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ'.]*(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][\wÀ-ÿ'.]*){0,5}"
        r",?\s*(?:n[º°o.]?\s*)?\d{1,5}(?:\s*[-,]\s*(?:apto?\.?|apartamento|bloco|casa|sala)\s*\w+)?"),
        confianca=0.85),
]


def reconhecer(texto: str) -> list[Entidade]:
    """Aplica todos os reconhecedores por regra (sem resolver sobreposições)."""
    norm = _sem_acento(texto)
    return [e for r in RECONHECEDORES for e in r.encontrar(texto, norm)]
