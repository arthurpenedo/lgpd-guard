from lgpd_guard.reconhecedores import reconhecer


def test_reconhecer_texto_sem_dado_pessoal_devolve_vazio():
    assert reconhecer("Bom dia, preciso da segunda via do boleto.") == []


def test_reconhecer_acha_cpf_e_email_com_posicoes_corretas():
    texto = "CPF 529.982.247-25 e e-mail ana@exemplo.com.br"
    achados = reconhecer(texto)
    assert {e.tipo for e in achados} == {"CPF", "EMAIL"}
    for e in achados:
        assert texto[e.inicio:e.fim] == e.texto
