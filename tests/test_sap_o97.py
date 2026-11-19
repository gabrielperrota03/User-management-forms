"""Report do O97 (sem SAP real). Linhas no formato da grade de 19/11/2026."""
from datetime import date, datetime, timedelta

import pytest

from gestao_usuarios.config import carregar
from gestao_usuarios.sap_gui import TelaInesperada
from gestao_usuarios.sap_o97 import (ConfigO97, atualizar_lista, interpretar_linhas, lista_plausivel,
                                     programa_confere)
from gestao_usuarios.zbr import ListaZbr

HOJE = date(2026, 11, 19)
C = ConfigO97()


def linha(igg="L1170904", role="ZBRCOORD", grupo="BR-TEP", de="12.11.2025 00:00:00", ate="31.12.9999 00:00:00",
          tipo="Business Role"):
    return {"GRACUSERROLE-USER_ID": igg, "GRACUSER-FIRST_NAME": "Gabriel", "GRACUSER-LAST_NAME": "PERROTA",
            "GRACUSERCONN-USER_GROUP": grupo, "GRACROLE-ROLE_NAME": role, "GRACROLET-DESCN": "Coordinator SAP",
            "TEXT_GRACROLE_ROLE_TYPE": tipo, "GRACUSERROLE-VALID_FROM": de, "GRACUSERROLE-VALID_TO": ate}


TOTAIS = {**linha(), "GRACUSERROLE-USER_ID": "", "GRACUSER-FIRST_NAME": "", "GRACUSER-LAST_NAME": "",
          "GRACUSERCONN-USER_GROUP": "", "GRACROLE-ROLE_NAME": "", "GRACROLET-DESCN": "", "TEXT_GRACROLE_ROLE_TYPE": "",
          "GRACUSERROLE-VALID_FROM": "65.55.*126 00:00:00", "GRACUSERROLE-VALID_TO": "55.61.*995 00:00:00"}


def test_config():
    c = ConfigO97.de_config(carregar(usar_local=False))
    assert (c.user_group, c.connector, c.transacao) == ("BR-TEP", "E1PCLNT010", "Z_USER_BR")
    assert c.entrada_logon == "001 - O97 : GRC : Production"


def test_linha_real_e_totais_ignorados():
    assert interpretar_linhas([linha(), TOTAIS], C, HOJE) == {"L1170904": ("ZBRCOORD",)}


def test_vigencia():
    linhas = [linha("L1111111", de="20.11.2026 00:00:00"), linha("L2222222", ate="18.11.2026 00:00:00"),
              linha("L3333333", de="19.11.2026 00:00:00", ate="19.11.2026 00:00:00")]
    assert interpretar_linhas(linhas, C, HOJE) == {"L1111111": (), "L2222222": (), "L3333333": ("ZBRCOORD",)}


def test_mais_de_um_zbr_fica_visivel():
    assert interpretar_linhas([linha(role="ZBRTAX"), linha(role="ZBRAUDIT")], C, HOJE) == {"L1170904": ("ZBRAUDIT", "ZBRTAX")}


@pytest.mark.parametrize("campos,trecho", [({"grupo": "FR-TEP"}, "grupo"), ({"tipo": "Technical Role"}, "tipo"),
                                           ({"de": "ontem"}, "data")])
def test_tela_diferente_da_mapeada(campos, trecho):
    with pytest.raises(TelaInesperada, match=trecho):
        interpretar_linhas([linha(**campos)], C, HOJE)


def test_coluna_faltando():
    l = linha()
    del l["GRACUSERCONN-USER_GROUP"]
    with pytest.raises(TelaInesperada, match="colunas"):
        interpretar_linhas([l], C, HOJE)


def test_programa_com_preenchimento_do_sap_query():
    assert programa_confere("AQZZZGRCREPORTS=Z_USER_BR=====", "AQZZZGRCREPORTS=Z_USER_BR")
    assert not programa_confere("SAPLSLVC_FULLSCREEN", "AQZZZGRCREPORTS=Z_USER_BR")
    assert not programa_confere("AQZZZGRCREPORTS=Z_USER_BR", "")


def test_lista_plausivel():
    antiga = ListaZbr(datetime(2026, 11, 12), {f"L{i:07d}": ("ZBRX",) for i in range(229)})
    assert lista_plausivel({}, antiga) == "a extração do O97 veio vazia"
    assert lista_plausivel({f"L{i:07d}": ("ZBRX",) for i in range(184)}, antiga) is None      # 80% de 229 = 183,2
    assert lista_plausivel({f"L{i:07d}": ("ZBRX",) for i in range(183)}, antiga) is not None
    assert "mantida" in lista_plausivel({f"L{i:07d}": ("ZBRX",) for i in range(150)}, antiga)
    assert lista_plausivel({"L1170904": ("ZBRCOORD",)}, None) is None


def test_atualizar_lista(tmp_path):
    caminho = tmp_path / "zbr.json"
    agora = datetime(2026, 11, 19, 7, 0)
    gravou, msg = atualizar_lista({"L1170904": ("ZBRCOORD",), "L1111111": ()}, caminho, agora)
    assert gravou and "2 usuários" in msg and "1 sem ZBR" in msg
    assert ListaZbr.carregar(caminho).usuarios == {"L1170904": ("ZBRCOORD",), "L1111111": ()}
    gravou, msg = atualizar_lista({}, caminho, agora + timedelta(days=7))
    assert not gravou and ListaZbr.carregar(caminho).gerado_em == agora, "lista atual mantida"
