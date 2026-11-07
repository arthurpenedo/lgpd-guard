from types import SimpleNamespace

import pytest

from lgpd_guard.nomes import (
    _eh_pessoa_plausivel,
    _passa_filtro_gramatical,
    reconhecer_nomes,
)


@pytest.mark.parametrize(("texto", "esperado"), [
    ("Maria Souza", True),
    ("  Maria Souza.", True),
    ("Itaú", False),             # banco, não pessoa
    ("Banco Inter", False),      # começa por termo de lista
    ("", False),
    ("...", False),
    ("Fulano 123", False),       # dígito: não é nome
    ("12345", False),
])
def test_eh_pessoa_plausivel(texto, esperado):
    assert _eh_pessoa_plausivel(texto) is esperado


def _ent(palavras, texto_depois="", pos="PROPN"):
    """Span falso: só os atributos que o filtro usa."""
    nome = " ".join(palavras)
    texto = nome + texto_depois
    tokens = [SimpleNamespace(pos_=pos) for _ in palavras]

    class Span(list):
        end_char = len(nome)
        doc = SimpleNamespace(text=texto)

    return Span(tokens)


def test_filtro_rejeita_verbo_no_inicio_da_frase():
    assert _passa_filtro_gramatical(_ent(["Quero"], pos="VERB")) is False


def test_filtro_rejeita_palavra_unica_que_nao_e_nome_proprio():
    assert _passa_filtro_gramatical(_ent(["Comprei"], pos="NOUN")) is False


def test_filtro_rejeita_sobrenome_de_razao_social():
    assert _passa_filtro_gramatical(_ent(["Fonseca", "Costa"], " S.A. abriu")) is False
    assert _passa_filtro_gramatical(_ent(["Silva"], " Ltda")) is False


def test_filtro_aceita_nome_proprio_comum():
    assert _passa_filtro_gramatical(_ent(["Maria", "Souza"], " ligou ontem")) is True


def test_reconhecer_nomes_sem_ner_so_usa_regra_de_contexto():
    achados = reconhecer_nomes("Meu nome é Maria Souza e moro em Osasco.", usar_ner=False)
    assert all(e.fonte == "regra+contexto" for e in achados)
