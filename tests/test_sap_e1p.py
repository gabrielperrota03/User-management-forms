"""SapE1PReal: SU01D e SUIM não geram print por padrão (decisão do analista, 23/11/2026)."""
from gestao_usuarios.config import carregar
from gestao_usuarios.sap_e1p import SapE1PReal, aba_logon_lida, esta_bloqueado, interpretar_logon
from gestao_usuarios.suim import ConfigSuim


class SessaoQueNaoPodeSerTocada:
    def findById(self, _):
        raise AssertionError("o print não devia tocar na janela do SAP")


def _sap(tmp_path, **kw):
    return SapE1PReal(SessaoQueNaoPodeSerTocada(), ConfigSuim.de_config(carregar(usar_local=False)), tmp_path, **kw)


def test_sem_print_por_padrao(tmp_path):
    sap = _sap(tmp_path)
    sap._print("su01d_L1234567.png")
    sap._print("suim_FB01.png")
    assert sap.prints == [] and list(tmp_path.iterdir()) == []


def test_print_so_com_a_flag(tmp_path):
    import pytest
    with pytest.raises(AssertionError, match="janela do SAP"):
        _sap(tmp_path, tirar_prints=True)._print("x.png")


def test_leitura_da_su01d():
    assert esta_bloqueado(["User is locked"]) and not esta_bloqueado(["Validity Period", "User Type"])
    assert aba_logon_lida(["Password Status"]) and not aba_logon_lida(["Address"])
    assert interpretar_logon(["Validity Period", "Password Status"]).bloqueado is False
    assert interpretar_logon(["User is locked", "User Type"]).bloqueado is True
    assert interpretar_logon(["Address"]).bloqueado is None, "aba não lida: bloqueio incerto"
