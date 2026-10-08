"""Validadores matemáticos: separam um CPF de verdade de qualquer número com 11 dígitos."""

from __future__ import annotations

import re


def digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def cpf_valido(texto: str) -> bool:
    d = digitos(texto)
    if len(d) != 11 or d == d[0] * 11:  # 111.111.111-11 passa no cálculo, mas não é emitido
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        verificador = (soma * 10) % 11 % 10
        if verificador != int(d[tamanho]):
            return False
    return True


def cnpj_valido(texto: str) -> bool:
    d = digitos(texto)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for tamanho, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(d[i]) * pesos[i] for i in range(tamanho)) % 11
        verificador = 0 if resto < 2 else 11 - resto
        if verificador != int(d[tamanho]):
            return False
    return True


def luhn_valido(texto: str) -> bool:
    """Algoritmo de Luhn, usado pelos números de cartão de crédito e débito."""
    d = digitos(texto)
    if not 13 <= len(d) <= 19 or d == d[0] * len(d):
        return False
    total = 0
    for i, c in enumerate(reversed(d)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def ddd_valido(ddd: str) -> bool:
    """DDDs brasileiros existentes (11 a 99, sem os não atribuídos)."""
    validos = {
        11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
        41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69,
        71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99,
    }
    return ddd.isdigit() and int(ddd) in validos
