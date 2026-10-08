"""Reconhecimento de nomes de pessoas: modelo de NER em português + regras de apoio.

O NER do spaCy (pt_core_news_sm) acha nomes em qualquer posição da frase, mas erra
com nomes de empresas, cidades e palavras em maiúsculas. As regras pegam os casos
em que o contexto não deixa dúvida ("meu nome é...", "Sra. ...") e filtram os falsos
positivos mais comuns em atendimento bancário.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .entidades import Entidade

_PALAVRA_NOME = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõçü]+"
_CONECTOR = r"(?:\s+(?:d[aeo]s?|e)\s+|\s+)"
_NOME_COMPLETO = rf"{_PALAVRA_NOME}(?:{_CONECTOR}{_PALAVRA_NOME}){{0,4}}"

# Só as palavras-gatilho ignoram maiúsculas; o nome em si precisa começar com maiúscula,
# senão "meu nome é joão e preciso de ajuda" viraria um nome de cinco palavras.
_GATILHOS = re.compile(
    rf"(?i:meu nome (?:é|e)|me chamo|eu sou (?:o|a)|sou (?:o|a)|nome:|titular:|cliente:|"
    rf"\b(?:sr|sra|srta|dr|dra)\.?|senhor|senhora|em nome de|favorecid[oa]:?|benefici[aá]ri[oa]:?|"
    rf"atenciosamente,?|att\.?,?|abraços,?|(?:o|a) (?:titular|responsável|correntista|portador[a]?) (?:é|e)|"
    rf"(?:meu|minha) (?:pai|mãe|mae|marido|esposa|esposo|filho|filha|irmão|irmao|irmã|irma|avô|avó),)"
    rf"\s+({_NOME_COMPLETO})"
)

# Termos que o NER costuma confundir com pessoas no contexto bancário.
_NAO_PESSOA = {
    "banco", "itau", "itaú", "bradesco", "santander", "caixa", "nubank", "inter", "pix", "ted", "doc",
    "visa", "mastercard", "elo", "aurora", "sao paulo", "são paulo", "rio", "brasil", "cpf", "cnpj",
    "rua", "avenida", "olá", "ola", "oi", "bom dia", "boa tarde", "boa noite", "obrigado", "obrigada",
    "prezado", "prezada", "atenciosamente", "cliente", "senhor", "senhora", "app", "sac",
}


def _eh_pessoa_plausivel(texto: str) -> bool:
    limpo = texto.strip(" .,;:").lower()
    if not limpo or limpo in _NAO_PESSOA or any(p in _NAO_PESSOA for p in limpo.split()[:1]):
        return False
    return any(c.isalpha() for c in limpo) and not any(c.isdigit() for c in limpo)


_SUFIXO_EMPRESA = re.compile(r"^\s*(?:S\.?A\.?|Ltda\.?|LTDA|EIRELI|ME\b|EPP\b|& Cia|e Filhos|Comércio|Comercio)")


def _passa_filtro_gramatical(ent) -> bool:  # ent: spacy.tokens.Span
    """O NER pequeno do spaCy marca como pessoa o verbo que abre a frase ("Quero", "Comprei")
    e sobrenomes que fazem parte de razão social ("Fonseca de Costa S.A."). A classe
    gramatical calculada pelo próprio modelo resolve isso sem lista de palavras."""
    if any(t.pos_ in ("VERB", "AUX") for t in ent):
        return False
    if len(ent) == 1 and ent[0].pos_ != "PROPN":
        return False
    return not _SUFIXO_EMPRESA.match(ent.doc.text[ent.end_char:ent.end_char + 15])


@lru_cache(maxsize=1)
def _carregar_spacy():
    try:
        import spacy

        # o morphologizer fica ligado: a classe gramatical é usada para filtrar falsos nomes
        return spacy.load("pt_core_news_sm", disable=["lemmatizer", "parser"])
    except Exception:  # spaCy ou o modelo ausentes: segue só com as regras
        return None


def spacy_disponivel() -> bool:
    return _carregar_spacy() is not None


def reconhecer_nomes(texto: str, usar_ner: bool = True) -> list[Entidade]:
    entidades: list[Entidade] = []
    for achado in _GATILHOS.finditer(texto):
        inicio, fim = achado.span(1)
        if _eh_pessoa_plausivel(texto[inicio:fim]):
            entidades.append(Entidade(inicio, fim, "NOME", texto[inicio:fim], 0.9, "regra+contexto"))

    nlp = _carregar_spacy() if usar_ner else None
    if nlp is not None:
        for ent in nlp(texto).ents:
            if ent.label_ == "PER" and _eh_pessoa_plausivel(ent.text) and _passa_filtro_gramatical(ent):
                # o NER às vezes inclui pontuação ou artigo nas bordas
                bruto = texto[ent.start_char:ent.end_char]
                inicio = ent.start_char + (len(bruto) - len(bruto.lstrip(" .,;:")))
                fim = ent.end_char - (len(bruto) - len(bruto.rstrip(" .,;:")))
                if fim > inicio:
                    entidades.append(Entidade(inicio, fim, "NOME", texto[inicio:fim], 0.8, "ner"))
    return entidades
