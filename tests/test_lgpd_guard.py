import pytest

from lgpd_guard import Cofre, Detector, Entidade, Pseudonimizador
from lgpd_guard import validadores as v
from lgpd_guard.avaliacao import avaliar, carregar, sistema_lgpd_guard
from lgpd_guard.cli import main

det = Detector(usar_ner=False)  # testes rodam sem depender do spaCy


def tipos(texto: str) -> list[tuple[str, str]]:
    return [(e.tipo, e.texto) for e in det.detectar(texto)]


# ---------------------------------------------------------------- validadores

@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "111.444.777-35"])
def test_cpf_valido(cpf):
    assert v.cpf_valido(cpf)


@pytest.mark.parametrize("cpf", ["529.982.247-26", "111.111.111-11", "123"])
def test_cpf_invalido(cpf):
    assert not v.cpf_valido(cpf)


def test_cnpj_e_luhn():
    assert v.cnpj_valido("11.222.333/0001-81")
    assert not v.cnpj_valido("11.222.333/0001-82")
    assert v.luhn_valido("4111 1111 1111 1111")
    assert not v.luhn_valido("4111 1111 1111 1112")


# ---------------------------------------------------------------- detecção

def test_detecta_os_documentos_brasileiros():
    achados = dict(tipos(
        "CPF 529.982.247-25, CNPJ 11.222.333/0001-81, cartão 4111 1111 1111 1111, "
        "RG 12.345.678-9, CEP 01310-100, placa ABC1D23, e-mail ana@exemplo.com.br"))
    assert set(achados) == {"CPF", "CNPJ", "CARTAO", "RG", "CEP", "PLACA", "EMAIL"}


def test_numero_parecido_com_cpf_nao_e_marcado():
    assert tipos("O protocolo do chamado é 12345678901 e o valor R$ 1.500,00.") == []


def test_onze_digitos_soltos_so_viram_telefone_com_contexto():
    assert tipos("Protocolo 22948662836.") == []
    assert tipos("Pode me ligar no 22948662836?") == [("TELEFONE", "22948662836")]


def test_telefone_com_mais_55_nao_vira_cartao():
    assert tipos("Celular: +55 19 99815-5786") == [("TELEFONE", "+55 19 99815-5786")]


def test_rg_e_nascimento_exigem_contexto():
    assert tipos("O código é 12.345.678-9 e vence em 12/03/2027.") == []
    assert ("RG", "12.345.678-9") in tipos("Meu RG é 12.345.678-9")
    assert ("DATA_NASCIMENTO", "12/03/1988") in tipos("Nasci em 12/03/1988")


def test_nome_por_gatilho_respeita_maiusculas():
    assert tipos("Meu nome é Ana Paula Souza e preciso de ajuda") == [("NOME", "Ana Paula Souza")]
    assert tipos("Atenciosamente, Bruno Lima") == [("NOME", "Bruno Lima")]
    assert tipos("meu nome é ana e preciso de ajuda") == []  # minúsculas ficam para o NER


def test_banco_e_cidade_nao_sao_pessoas():
    assert tipos("Sou cliente do Banco do Brasil em São Paulo.") == []


def test_sem_sobreposicao():
    entidades = det.detectar("Cliente: Maria Souza, CPF 52998224725, fone (11) 98765-4321")
    for a, b in zip(entidades, entidades[1:]):
        assert not a.sobrepoe(b)


def test_tipo_desconhecido():
    with pytest.raises(ValueError):
        Detector(tipos=["SENHA"])
    with pytest.raises(ValueError):
        Entidade(0, 3, "SENHA", "abc")


# ---------------------------------------------------------------- pseudonimização

def test_ida_e_volta_preserva_o_texto():
    p = Pseudonimizador(det)
    texto = "Meu nome é Ana Lima, CPF 529.982.247-25, e-mail ana@exemplo.com."
    r = p.anonimizar(texto)
    assert "529.982" not in r.texto and "Ana Lima" not in r.texto and "<CPF_1>" in r.texto
    assert p.restaurar(r.texto, r.cofre) == texto


def test_mesmo_valor_mesmo_marcador_mesmo_formatado_diferente():
    r = Pseudonimizador(det).anonimizar("CPF 529.982.247-25 ou 52998224725? O outro é 111.444.777-35")
    assert r.texto.count("<CPF_1>") == 2 and "<CPF_2>" in r.texto


def test_cofre_compartilhado_entre_mensagens():
    p, cofre = Pseudonimizador(det), Cofre()
    p.anonimizar("Meu CPF é 529.982.247-25", cofre)
    segunda = p.anonimizar("Confirma o CPF 52998224725?", cofre)
    assert "<CPF_1>" in segunda.texto and len(cofre) == 1


def test_restaurar_resposta_do_llm_e_ignorar_marcador_inventado():
    p = Pseudonimizador(det)
    r = p.anonimizar("Meu CPF é 529.982.247-25")
    resposta = "Encontrei o cadastro <CPF_1>. Já o <CPF_9> não existe."
    assert p.restaurar(resposta, r.cofre) == "Encontrei o cadastro 529.982.247-25. Já o <CPF_9> não existe."


def test_mascara_para_logs():
    assert Pseudonimizador(det).mascarar("CPF 529.982.247-25") == "CPF [CPF ***25]"


# ---------------------------------------------------------------- benchmark e CLI

def test_benchmark_regras_no_conjunto_de_desenvolvimento():
    r = avaliar("regras", sistema_lgpd_guard(False), carregar("dados/teste.jsonl"))
    assert r.geral.precisao >= 0.99
    for tipo in ("CPF", "CNPJ", "CARTAO", "EMAIL", "PIX_ALEATORIA"):
        assert r.por_tipo[tipo].f1 == 1.0
    assert r.textos_limpos_marcados == 0


def test_cli_anonimizar(capsys):
    assert main(["anonimizar", "--sem-ner", "Meu CPF é 529.982.247-25"]) == 0
    assert capsys.readouterr().out.strip() == "Meu CPF é <CPF_1>"


def test_cli_benchmark_gera_relatorio(tmp_path):
    saida = tmp_path / "index.html"
    assert main(["benchmark", "--sem-presidio", "--html", str(saida), "--json", str(tmp_path / "r.json")]) == 0
    assert "Conjunto de desafio" in saida.read_text(encoding="utf-8")
