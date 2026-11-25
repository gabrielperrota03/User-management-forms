"""RFC somente leitura: lista fechada de funções/tabelas, parâmetros de conexão, leitura do usuário (SU01D sem tela)."""
import pytest

from gestao_usuarios import rfc_sap
from gestao_usuarios.conexoes import ConexoesReais
from gestao_usuarios.decisao import UsuarioSap
from gestao_usuarios.erros import SessaoParada
from gestao_usuarios.rfc_sap import ErroRFC, FuncaoNaoPermitida, Rfc, conferir_chamada
from gestao_usuarios.sap_e1p_rfc import SapE1PRfc, interpretar_detalhe


# ------------------------------------------------------------------ a trava da regra 1
@pytest.mark.parametrize("funcao", ["BAPI_USER_LOCK", "BAPI_USER_UNLOCK", "BAPI_USER_CHANGE", "BAPI_USER_DELETE",
                                    "RFC_SYSTEM_INFO", "SUSR_USER_CHANGE_PASSWORD", "RFC_ABAP_INSTALL_AND_RUN", ""])
def test_funcao_fora_da_lista_e_recusada(funcao):
    with pytest.raises(FuncaoNaoPermitida):
        conferir_chamada(funcao, {"USERNAME": "L1234567"})


def test_read_table_so_nas_tabelas_permitidas():
    conferir_chamada("RFC_READ_TABLE", {"QUERY_TABLE": "AGR_1251"})
    conferir_chamada("rfc_read_table", {"QUERY_TABLE": "agr_1251"})
    for tabela in ("USR02", "PA0008", "AGR_USERS", "", None):
        with pytest.raises(FuncaoNaoPermitida, match="tabela"):
            conferir_chamada("RFC_READ_TABLE", {"QUERY_TABLE": tabela})
    with pytest.raises(FuncaoNaoPermitida):
        conferir_chamada("RFC_READ_TABLE")


def test_leitura_do_usuario_e_permitida():
    conferir_chamada("BAPI_USER_GET_DETAIL", {"USERNAME": "L1234567"})


def test_rfc_chamar_recusa_antes_de_falar_com_o_sap():
    rfc = Rfc.__new__(Rfc)                               # sem DLL e sem conexão: se tocar em qualquer coisa, quebra com AttributeError
    with pytest.raises(FuncaoNaoPermitida):
        rfc.chamar("BAPI_USER_LOCK", {"USERNAME": "L1234567"})


# ------------------------------------------------------------------ funções puras
def test_quebrar_filtro_em_linhas_de_ate_72():
    linhas = rfc_sap.quebrar_filtro("OBJECT = 'S_TCODE' AND FIELD = 'TCD' AND AGR_NAME LIKE 'Y-%' AND DELETED = ' ' AND LOW <> 'X'")
    assert all(len(x) <= 72 for x in linhas) and " ".join(linhas).startswith("OBJECT = 'S_TCODE'")
    with pytest.raises(ErroRFC):
        rfc_sap.quebrar_filtro("X" * 80)


def test_cortar_linha_pelas_posicoes():
    layout = [("AGR_NAME", 0, 10), ("LOW", 10, 6), ("DELETED", 16, 1)]
    assert rfc_sap.cortar_linha("Y-BRF-FB01FB01  X", layout) == ["Y-BRF-FB01", "FB01", "X"]


def test_parametros_com_message_server_e_snc():
    svc = {"systemid": "E1M", "name": "E1M", "server": "PUBLIC", "msid": "m1", "routerid": "r1",
           "sncname": "p:CN=KerberosE1MT, O=TOTAL, C=FR", "sncop": "9"}
    p = rfc_sap.montar_parametros(svc, {"m1": {"host": "sape1m.main.glb.corp.local", "port": "3601"}},
                                  {"r1": "/H/SR2/H/SR7"}, "010", "EN", "C:/sapcrypto.dll")
    assert p["mshost"] == "sape1m.main.glb.corp.local" and p["group"] == "PUBLIC" and p["saprouter"] == "/H/SR2/H/SR7"
    assert p["snc_mode"] == "1" and p["snc_partnername"].startswith("p:CN=") and p["client"] == "010"
    assert "passwd" not in p and "user" not in p, "sem senha nem usuário: login pelo SSO do Windows"


def test_entrada_sem_snc_nao_conecta():
    with pytest.raises(ErroRFC, match="SNC"):
        rfc_sap.montar_parametros({"systemid": "X", "name": "X", "server": "h:3200"}, {}, {}, "010", "EN", "lib")


# ------------------------------------------------------------------ interpretação do RETURN
def test_interpretar_detalhe():
    nao_existe = [{"TYPE": "E", "ID": "01", "NUMBER": "124", "MESSAGE": "User L0000000 does not exist"}]
    assert interpretar_detalhe(nao_existe, None) == UsuarioSap(existe=False)
    outro_erro = [{"TYPE": "E", "ID": "S#", "NUMBER": "001", "MESSAGE": "sem autorização"}]
    assert interpretar_detalhe(outro_erro, None) == UsuarioSap(existe=None), "erro que não é 'não existe' = incerto"
    assert interpretar_detalhe([{"TYPE": "A", "ID": "XX", "NUMBER": "000", "MESSAGE": ""}], None).existe is None
    assert interpretar_detalhe([], {"LOCAL_LOCK": "U", "GLOB_LOCK": "U"}) == UsuarioSap(True, False)
    assert interpretar_detalhe([], {"LOCAL_LOCK": "L", "GLOB_LOCK": "U"}) == UsuarioSap(True, True)
    assert interpretar_detalhe([], {"LOCAL_LOCK": "U", "GLOB_LOCK": "L"}).bloqueado is True
    assert interpretar_detalhe([{"TYPE": "W", "ID": "", "NUMBER": "", "MESSAGE": "aviso"}], None) == UsuarioSap(True, None)


# ------------------------------------------------------------------ SapE1PRfc com um RFC falso
class RfcFalso:
    def __init__(self, usuarios=None, quebrar_em=None):
        self.usuarios, self.quebrar_em = usuarios or {}, quebrar_em
        self.chamadas, self.fechado = [], False

    def chamar(self, funcao, entradas=None, tabelas=None):
        self.chamadas.append((funcao, entradas["USERNAME"]))
        if entradas["USERNAME"] == self.quebrar_em:
            raise ErroRFC("conexão caiu")
        return entradas["USERNAME"]

    def tabela(self, f, nome, campos):
        if self.usuarios.get(f) is None:
            return [{"TYPE": "E", "ID": "01", "NUMBER": "124", "MESSAGE": f"User {f} does not exist"}]
        return []

    def estrutura(self, f, nome, campos):
        return {"LOCAL_LOCK": "L" if self.usuarios[f] == "bloqueado" else "U", "GLOB_LOCK": "U"}

    def destruir(self, f):
        pass

    def fechar(self):
        self.fechado = True


def test_usuario_por_rfc():
    rfc = RfcFalso({"L1234567": "livre", "L7654321": "bloqueado"})
    sap = SapE1PRfc(abrir=lambda: rfc)
    assert sap.usuario("l1234567") == UsuarioSap(True, False)          # maiúsculas, como a SU01D
    assert sap.usuario("L7654321") == UsuarioSap(True, True)
    assert sap.usuario("L0000000") == UsuarioSap(False)
    assert [c[0] for c in rfc.chamadas] == ["BAPI_USER_GET_DETAIL"] * 3


def test_falha_na_leitura_e_incerta_e_reconecta():
    abertas = []

    def abrir():
        abertas.append(1)
        return RfcFalso({"L1234567": "livre"}, quebrar_em="L9999999")

    sap = SapE1PRfc(abrir=abrir)
    assert sap.usuario("L9999999") == UsuarioSap(existe=None) and sap.avisos
    assert sap.usuario("L1234567") == UsuarioSap(True, False) and len(abertas) == 2      # reabriu depois da queda
    sap.limpar(None)
    assert sap.avisos == []


def test_falha_ao_conectar_para_a_rodada():
    def abrir():
        raise ErroRFC("sem rede")

    with pytest.raises(SessaoParada, match="RFC do E1P indisponível"):
        SapE1PRfc(abrir=abrir).usuario("L1234567")


# ------------------------------------------------------------------ conexões: o modo rfc não abre o SAP GUI
def test_modo_rfc_nao_abre_sessao_sap_gui(monkeypatch):
    from gestao_usuarios import conexoes

    def proibido(*a, **k):
        raise AssertionError("o modo rfc não pode abrir o SAP GUI")

    monkeypatch.setattr(conexoes.sap_gui, "SessaoPropria", proibido)
    c = ConexoesReais({"sap": {"modo_usuario": "rfc", "conexao_e1p": "x"}, "rfc": {"sistema": "E1P", "mandante": 10}})
    sap = c.sap()
    assert isinstance(sap, SapE1PRfc) and sap.sistema == "E1P" and sap.mandante == "10" and c.sap() is sap
    c.fechar()


def test_modo_padrao_e_gui(monkeypatch):
    from gestao_usuarios import conexoes
    aberto = []

    class Sessao:
        def __init__(self, *a):
            aberto.append(a)

        def __enter__(self):
            return object()

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(conexoes.sap_gui, "SessaoPropria", Sessao)
    monkeypatch.setattr(ConexoesReais, "_indice_roles", lambda self: object())
    monkeypatch.setattr(conexoes, "SapE1PReal", lambda *a, **k: object())
    monkeypatch.setattr(conexoes, "ConfigSuim", type("ConfigFalsa", (), {"de_config": staticmethod(lambda cfg: object())}))
    c = ConexoesReais({"sap": {"conexao_e1p": "E1P entrada"}, "suim": {}})
    c.sap()
    assert aberto == [("E1P", "E1P entrada")]
