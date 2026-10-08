"""Linha de comando: anonimizar textos e rodar o benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detector import Detector
from .pseudonimizador import Pseudonimizador

EXEMPLO = ("Olá, meu nome é Maria Helena Duarte, CPF 529.982.247-25. Meu cartão 4111 1111 1111 1111 foi "
           "clonado. Moro na Rua das Flores, 123, CEP 01310-100. Me liga no (11) 98765-4321 ou manda e-mail "
           "para maria.duarte@gmail.com. O protocolo é 12345678901.")


def _anonimizar(args: argparse.Namespace) -> int:
    texto = args.texto if args.texto != "-" else sys.stdin.read()
    p = Pseudonimizador(Detector(usar_ner=not args.sem_ner))
    if args.mascarar:
        print(p.mascarar(texto))
        return 0
    r = p.anonimizar(texto)
    print(r.texto)
    if args.mostrar:
        for e in r.entidades:
            print(f"  {e.tipo:<16} {e.texto!r} ({e.fonte}, {e.confianca})", file=sys.stderr)
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    from . import relatorio
    from .avaliacao import avaliar, carregar, sistema_lgpd_guard, sistema_presidio

    sistemas = {"lgpd-guard (regras)": sistema_lgpd_guard(usar_ner=False)}
    if Detector().ner_ativo:
        sistemas["lgpd-guard (regras + NER)"] = sistema_lgpd_guard(usar_ner=True)
    else:
        print("spaCy/pt_core_news_sm indisponível: pulando 'regras + NER'.", file=sys.stderr)
    if not args.sem_presidio:
        try:
            sistemas["Presidio (Microsoft), pt"] = sistema_presidio()
        except Exception as erro:  # noqa: BLE001 - benchmark segue sem o Presidio
            print(f"Presidio indisponível ({erro.__class__.__name__}): pulando.", file=sys.stderr)

    resultados: dict[str, dict[str, dict]] = {}
    for rotulo, caminho in (("Conjunto de desenvolvimento", args.dev), ("Conjunto de desafio", args.desafio)):
        if not caminho or not Path(caminho).exists():
            continue
        exemplos = carregar(caminho)
        resultados[f"{rotulo} ({len(exemplos)} textos)"] = {}
        for nome, sistema in sistemas.items():
            a = avaliar(nome, sistema, exemplos).to_dict()
            resultados[f"{rotulo} ({len(exemplos)} textos)"][nome] = a
            print(f"{rotulo:<28} {nome:<28} F1 {a['geral']['f1']:.3f}  P {a['geral']['precisao']:.3f}  "
                  f"R {a['geral']['cobertura']:.3f}  protegidos {a['protecao']['cobertura']:.1%}")

    if args.json:
        Path(args.json).write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.html:
        r = Pseudonimizador().anonimizar(EXEMPLO)
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(relatorio.gerar(resultados, (EXEMPLO, r.texto)), encoding="utf-8")
        print(f"Relatório salvo em {args.html}")
    return 0


def _proxy(args: argparse.Namespace) -> int:
    import uvicorn

    from .proxy import criar_app

    app = criar_app(upstream=args.upstream, usar_ner=not args.sem_ner)
    print(f"lgpd-guard proxy em http://{args.host}:{args.porta}/v1  ->  {args.upstream}")
    uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgpd-guard", description="Dados pessoais brasileiros fora do LLM.")
    parser.add_argument("--version", action="version", version=f"lgpd-guard {__version__}")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("anonimizar", help="troca os dados pessoais por marcadores (ou máscaras)")
    p.add_argument("texto", help="texto a anonimizar ('-' lê da entrada padrão)")
    p.add_argument("--mascarar", action="store_true", help="máscara irreversível, para logs")
    p.add_argument("--mostrar", action="store_true", help="lista as entidades encontradas")
    p.add_argument("--sem-ner", action="store_true", help="só regras, sem o modelo de nomes")
    p.set_defaults(func=_anonimizar)

    p = sub.add_parser("benchmark", help="compara lgpd-guard e Presidio nos conjuntos rotulados")
    p.add_argument("--dev", default="dados/teste.jsonl")
    p.add_argument("--desafio", default="dados/desafio.jsonl")
    p.add_argument("--json")
    p.add_argument("--html")
    p.add_argument("--sem-presidio", action="store_true")
    p.set_defaults(func=_benchmark)

    p = sub.add_parser("proxy", help="sobe o proxy compatível com a API de chat da OpenAI")
    p.add_argument("--upstream", default="http://localhost:11434/v1", help="URL base do provedor de LLM")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--sem-ner", action="store_true")
    p.set_defaults(func=_proxy)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
