"""Leitura do resultado da simulação no GRC (sem GRC real). Linhas conforme a tela de 17/11/2026."""
import pytest

from gestao_usuarios import wd
from gestao_usuarios.analise import Risco
from gestao_usuarios.config import carregar
from gestao_usuarios.grc_risco import (ConfigGrcRisco, conferir_total, criterios_conferem, juntar,
                                       riscos_das_linhas)
from gestao_usuarios.sap_gui import TelaInesperada

SEM_VIOLACAO = {"User ID": "L1170904", "User Name": "Gabriel PERROTA", "User Group": "BR-TEP", "Access Risk ID": "",
                "System": "E1PCLNT010", "Action": "No Violations", "Execution Count": "0"}
SF028 = {"User ID": "L1170904", "Access Risk ID": "SF028_EP", "System": "E1PCLNT010", "Rule ID": "0004",
         "Risk Description": "Adjust the subsidiary balance using the vendor invoice entry and then cover it up using "
                             "journal entries.", "Risk Level": "Medium", "Action": "FB01", "Action Description": "Post Document",
         "Business Process": "EP_FIN"}


def test_sem_violacao_nao_e_risco():
    assert riscos_das_linhas([SEM_VIOLACAO], "Critical Action") == ()


def test_risco_real_e_repeticao_por_acao():
    outra_acao = {**SF028, "Rule ID": "0005", "Action": "FB60"}
    riscos = riscos_das_linhas([SF028, outra_acao], "Permission Level")
    assert riscos == (Risco("SF028_EP", SF028["Risk Description"], "Medium"),)


def test_linha_sem_id_e_sem_no_violations_e_tela_desconhecida():
    with pytest.raises(TelaInesperada, match="sem Access Risk ID"):
        riscos_das_linhas([{**SEM_VIOLACAO, "Action": "Error"}], "Permission Level")


def test_total_maior_que_a_tela_nao_vale_como_lido():
    conferir_total(1, 1, "x")
    conferir_total(0, 0, "x")
    with pytest.raises(TelaInesperada, match="foram lidas 10"):
        conferir_total(14, 10, "Permission Level")
    with pytest.raises(TelaInesperada, match="não identificado"):
        conferir_total(None, 1, "x")


def test_juntar_tipos_sem_repetir():
    a, b = Risco("A", "a", "High"), Risco("B", "b", "Critical")
    assert juntar({"Critical Action": (b,), "Permission Level": (a, b)}) == (b, a)
    assert juntar({"Critical Action": (), "Permission Level": ()}) == ()


def test_rule_set_e_obrigatorio():
    c = ConfigGrcRisco.de_config(carregar(usar_local=False))
    assert c.rule_set == "EP - SOD 2019" and c.url.startswith("https://sapo97")
    certo = {"System": "E1PCLNT010", "User": "l1170904", "Rule Set": "EP - SOD 2019"}
    assert criterios_conferem(certo, c, "L1170904") == []
    padrao_da_tela = {**certo, "Rule Set": "Total Worldwide - Global Rule Set"}
    assert any("Rule Set" in d for d in criterios_conferem(padrao_da_tela, c, "L1170904"))
    assert any("User" in d for d in criterios_conferem({**certo, "User": "L0000000"}, c, "L1170904"))


def test_somente_simulacao_ligado_por_padrao():
    assert ConfigGrcRisco.de_config(carregar(usar_local=False)).somente_simulacao is True


def test_estado_da_caixa_pelas_classes_reais():
    base = "lsSelector--generic lsSelector--text lsSelector--shrinked lsSelector--pushedToStart--spacing "
    assert wd.estado_da_caixa(base + "lsCheckBox--checked", "x") is True
    assert wd.estado_da_caixa(base + "lsCheckBox--unchecked  ", "x") is False, "'unchecked' contém 'checked'"
    with pytest.raises(TelaInesperada, match="não reconhecido"):
        wd.estado_da_caixa(base, "x")
    with pytest.raises(TelaInesperada, match="não encontrada"):
        wd.estado_da_caixa(None, "x")


@pytest.mark.parametrize("texto", ["Save", "Mitigate Risk", " run in background ", "Submit", "Delete"])
def test_botoes_proibidos(texto):
    with pytest.raises(wd.BotaoProibido):
        wd.clicar_botao(None, None, texto)
