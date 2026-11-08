"""Sistemas comparados em avaliacao.py: lgpd-guard real e Presidio simulado (sem instalar Presidio)."""

import sys
from types import ModuleType, SimpleNamespace

from lgpd_guard import avaliacao


def test_sistema_lgpd_guard_devolve_spans_com_tipo():
    detectar = avaliacao.sistema_lgpd_guard(usar_ner=False)
    texto = "meu cpf é 529.982.247-25"
    spans = detectar(texto)
    assert any(tipo == "CPF" and texto[i:f] == "529.982.247-25" for i, f, tipo in spans)


def _presidio_falso(monkeypatch, entidades):
    """Instala módulos falsos de presidio_analyzer; `entidades` é o que o 'motor' devolve."""
    raiz = ModuleType("presidio_analyzer")
    nlp_mod = ModuleType("presidio_analyzer.nlp_engine")
    pre = ModuleType("presidio_analyzer.predefined_recognizers")

    class Registro:
        def __init__(self, supported_languages):
            self.adicionados = []

        def add_recognizer(self, rec):
            self.adicionados.append(rec)

    class Motor:
        def __init__(self, nlp_engine, registry, supported_languages):
            self.registry = registry

        def analyze(self, text, language):
            assert language == "pt"
            return entidades

    class Provider:
        def __init__(self, nlp_configuration):
            assert nlp_configuration["models"][0]["lang_code"] == "pt"

        def create_engine(self):
            return object()

    raiz.AnalyzerEngine, raiz.RecognizerRegistry = Motor, Registro
    nlp_mod.NlpEngineProvider = Provider
    for nome in ("CreditCard", "Date", "Email", "Iban", "Phone", "Spacy"):
        setattr(pre, f"{nome}Recognizer", lambda **kw: SimpleNamespace(**kw))
    for nome, mod in (("presidio_analyzer", raiz), ("presidio_analyzer.nlp_engine", nlp_mod),
                      ("presidio_analyzer.predefined_recognizers", pre)):
        monkeypatch.setitem(sys.modules, nome, mod)


def test_presidio_mapeia_entidades_e_ignora_as_que_nao_conhece(monkeypatch):
    ent = [
        SimpleNamespace(entity_type="PERSON", start=0, end=4),
        SimpleNamespace(entity_type="EMAIL_ADDRESS", start=10, end=20),
        SimpleNamespace(entity_type="US_SSN", start=30, end=40),  # sem equivalente nosso
    ]
    _presidio_falso(monkeypatch, ent)
    assert avaliacao.sistema_presidio()("qualquer texto") == [(0, 4, "NOME"), (10, 20, "EMAIL")]


def test_presidio_sem_entidades_devolve_lista_vazia(monkeypatch):
    _presidio_falso(monkeypatch, [])
    assert avaliacao.sistema_presidio()("nada aqui") == []


def test_mapa_do_presidio_nao_cobre_documentos_brasileiros():
    # a lacuna que o lgpd-guard preenche: Presidio não tem CPF, CNPJ, RG nem CEP
    assert not {"CPF", "CNPJ", "RG", "CEP"} & set(avaliacao._PRESIDIO_PARA_NOSSO.values())
