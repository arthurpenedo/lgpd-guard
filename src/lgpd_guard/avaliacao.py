"""Benchmark: precisão, cobertura (recall) e F1 por tipo, contra um conjunto rotulado.

Duas formas de contar acerto:
- por tipo: o trecho detectado se sobrepõe ao rotulado E o tipo bate (mede o detector);
- proteção: qualquer detecção que cubra o dado conta, seja qual for o tipo. É o que importa
  para anonimizar: se um CPF foi escondido como "TELEFONE", ele não vazou do mesmo jeito.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Span = tuple[int, int, str]
Sistema = Callable[[str], list[Span]]


def carregar(caminho: str | Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def _sobrepoe(a: Span, b: Span) -> bool:
    return a[0] < b[1] and b[0] < a[1]


@dataclass
class Placar:
    vp: int = 0  # verdadeiros positivos
    fp: int = 0
    fn: int = 0

    @property
    def precisao(self) -> float:
        return self.vp / (self.vp + self.fp) if self.vp + self.fp else 0.0

    @property
    def cobertura(self) -> float:
        return self.vp / (self.vp + self.fn) if self.vp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precisao, self.cobertura
        return 2 * p * r / (p + r) if p + r else 0.0

    def to_dict(self) -> dict:
        return {"vp": self.vp, "fp": self.fp, "fn": self.fn, "precisao": round(self.precisao, 4),
                "cobertura": round(self.cobertura, 4), "f1": round(self.f1, 4)}


@dataclass
class Avaliacao:
    sistema: str
    geral: Placar = field(default_factory=Placar)
    por_tipo: dict[str, Placar] = field(default_factory=lambda: defaultdict(Placar))
    protecao: Placar = field(default_factory=Placar)
    textos_limpos_marcados: int = 0  # textos sem nenhum dado pessoal em que algo foi marcado
    textos_limpos: int = 0
    ms_por_texto: float = 0.0
    erros: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sistema": self.sistema, "geral": self.geral.to_dict(), "protecao": self.protecao.to_dict(),
            "por_tipo": {t: p.to_dict() for t, p in sorted(self.por_tipo.items())},
            "falsos_alarmes_em_textos_limpos": f"{self.textos_limpos_marcados}/{self.textos_limpos}",
            "ms_por_texto": round(self.ms_por_texto, 2), "erros": self.erros[:40],
        }


def avaliar(nome: str, sistema: Sistema, exemplos: list[dict]) -> Avaliacao:
    resultado = Avaliacao(nome)
    inicio = time.perf_counter()
    for ex in exemplos:
        ouro = [tuple(e) for e in ex["entidades"]]
        previsto = sistema(ex["texto"])
        if not ouro:
            resultado.textos_limpos += 1
            if previsto:
                resultado.textos_limpos_marcados += 1

        usados: set[int] = set()
        for o in ouro:
            achou = next((i for i, p in enumerate(previsto) if i not in usados and p[2] == o[2] and _sobrepoe(p, o)), None)
            if achou is None:
                resultado.geral.fn += 1
                resultado.por_tipo[o[2]].fn += 1
                resultado.erros.append({"id": ex["id"], "erro": "não detectado", "tipo": o[2], "trecho": ex["texto"][o[0]:o[1]]})
            else:
                usados.add(achou)
                resultado.geral.vp += 1
                resultado.por_tipo[o[2]].vp += 1
        for i, p in enumerate(previsto):
            if i not in usados:
                resultado.geral.fp += 1
                resultado.por_tipo[p[2]].fp += 1
                if not any(_sobrepoe(p, o) for o in ouro):
                    resultado.erros.append({"id": ex["id"], "erro": "falso alarme", "tipo": p[2], "trecho": ex["texto"][p[0]:p[1]]})

        # proteção: independente do tipo
        for o in ouro:
            if any(_sobrepoe(p, o) for p in previsto):
                resultado.protecao.vp += 1
            else:
                resultado.protecao.fn += 1
        resultado.protecao.fp += sum(1 for p in previsto if not any(_sobrepoe(p, o) for o in ouro))
    resultado.ms_por_texto = (time.perf_counter() - inicio) * 1000 / max(1, len(exemplos))
    return resultado


# ------------------------------------------------------------------ sistemas comparados

def sistema_lgpd_guard(usar_ner: bool) -> Sistema:
    from .detector import Detector

    detector = Detector(usar_ner=usar_ner)
    return lambda texto: [(e.inicio, e.fim, e.tipo) for e in detector.detectar(texto)]


# Presidio fala outros nomes de entidade; mapeamos para os nossos tipos.
_PRESIDIO_PARA_NOSSO = {
    "PERSON": "NOME", "EMAIL_ADDRESS": "EMAIL", "CREDIT_CARD": "CARTAO", "PHONE_NUMBER": "TELEFONE",
    "DATE_TIME": "DATA_NASCIMENTO", "LOCATION": "ENDERECO", "IBAN_CODE": "CONTA_BANCARIA",
}


def sistema_presidio() -> Sistema:
    """Presidio (Microsoft) configurado para português, com todos os reconhecedores genéricos.

    Não existe reconhecedor brasileiro no Presidio (nenhum CPF, CNPJ, RG ou CEP), então
    esses tipos ficam sem cobertura: é exatamente a lacuna que o lgpd-guard preenche.
    """
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import (
        CreditCardRecognizer, DateRecognizer, EmailRecognizer, IbanRecognizer, PhoneRecognizer, SpacyRecognizer,
    )

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": [{"lang_code": "pt", "model_name": "pt_core_news_sm"}],
    }).create_engine()
    registro = RecognizerRegistry(supported_languages=["pt"])
    for rec in (EmailRecognizer(supported_language="pt"), CreditCardRecognizer(supported_language="pt"),
                PhoneRecognizer(supported_language="pt", supported_regions=["BR"]),
                DateRecognizer(supported_language="pt"), IbanRecognizer(supported_language="pt"),
                SpacyRecognizer(supported_language="pt")):
        registro.add_recognizer(rec)
    motor = AnalyzerEngine(nlp_engine=nlp, registry=registro, supported_languages=["pt"])

    def detectar(texto: str) -> list[Span]:
        spans = []
        for r in motor.analyze(text=texto, language="pt"):
            tipo = _PRESIDIO_PARA_NOSSO.get(r.entity_type)
            if tipo:
                spans.append((r.start, r.end, tipo))
        return spans

    return detectar
