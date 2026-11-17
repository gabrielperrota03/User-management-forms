"""SUIM com um SAP falso: navegação gravada, conferências e leitura da grade (sem SAP real).
Valores das telas e da grade conforme a inspeção ao vivo de 17/11/2026 (FB01 no E1P/010)."""
import pytest

from gestao_usuarios import sap_gui, suim
from gestao_usuarios.config import carregar
from gestao_usuarios.sap_gui import TelaInesperada
from gestao_usuarios.suim import RoleSuim, TipoRole

POPUP_REAL = "Information | 523 roles with missing authorization not | displayed"
LINHAS_REAIS = [
    {"AGR_NAME": "Y-BRF-FB01-POST_DOCUMENT", "TYPE_ICON": "@IC\\QSin", "AGR_TEXT": "Post Document"},
    {"AGR_NAME": "Y-BRA-DEPRECIATION_PROCESSING", "TYPE_ICON": "@IC\\QSin", "AGR_TEXT": "Asset Depreciation Processing"},
]
LINHAS_COMPOSITE = [
    {"AGR_NAME": "z-brf-comp", "TYPE_ICON": "@IC\\QCom", "AGR_TEXT": "C"},
    {"AGR_NAME": "Z-BRA-COMP", "TYPE_ICON": "@IC\\QComposite Role@", "AGR_TEXT": "A"},
    {"AGR_NAME": "Z-BRF-COMP", "TYPE_ICON": "@IC\\QCom", "AGR_TEXT": "C"},
]


def cfg_suim(**extra) -> suim.ConfigSuim:
    cfg = carregar(usar_local=False)
    cfg["suim"].update(extra)
    return suim.ConfigSuim.de_config(cfg)


class Colecao:
    def __init__(self, itens):
        self.itens = list(itens)
        self.Count = len(self.itens)

    def Item(self, i):
        return self.itens[i]


class GradeFalsa:
    TITULOS = {"AGR_NAME": "Role", "TYPE_ICON": "Type", "AGR_TEXT": "Short Role Description"}

    def __init__(self, linhas, visiveis=2):
        self.linhas = linhas
        self.ColumnOrder = Colecao(linhas[0].keys() if linhas else self.TITULOS)
        self.RowCount = len(linhas)
        self.VisibleRowCount = visiveis
        self.firstVisibleRow = 0

    def GetDisplayedColumnTitle(self, c):
        return self.TITULOS.get(c, c)

    def GetCellValue(self, r, c):
        if not (self.firstVisibleRow <= r < self.firstVisibleRow + self.VisibleRowCount):
            raise RuntimeError("linha fora da tela ainda não carregada")
        return self.linhas[r][c]


class Componente:
    def __init__(self, texto=""):
        self.text = texto
        self.Text = texto
        self.pressionado = 0

    def press(self):
        self.pressionado += 1

    def sendVKey(self, k):
        pass


class ArvoreFalsa:
    def __init__(self):
        self.expandidos, self.clicados = [], []

    def expandNode(self, no):
        self.expandidos.append(no)

    def selectItem(self, no, item):
        pass

    def clickLink(self, no, item):
        self.clicados.append(no)


class Info:
    def __init__(self, programa):
        self.Program = programa


class SessaoFalsa:
    Busy = False

    def __init__(self, c: suim.ConfigSuim, titulo="Roles by Complex Selection Criteria", programa="RSUSR070",
                 popup=POPUP_REAL, linhas=LINHAS_REAIS):
        self.Info = Info(programa)
        self.arvore = ArvoreFalsa()
        self.grade = GradeFalsa(linhas)
        self.popup = popup
        self.comps = {"wnd[0]/tbar[0]/okcd": Componente(), "wnd[0]": Componente(titulo), c.campo_objeto: Componente(),
                      c.campo_valor: Componente(), "wnd[0]/tbar[1]/btn[8]": Componente(), c.arvore: self.arvore,
                      c.grade: self.grade, "wnd[1]/tbar[0]/btn[0]": Componente()}

    def findById(self, id_):
        if id_ == "wnd[1]":
            if self.popup is None:
                raise RuntimeError("sem popup")
            titulo, _, resto = self.popup.partition(" | ")
            janela = Componente(titulo)
            usr = Componente(resto)
            janela.findById = lambda _: usr
            return janela
        return self.comps[id_]


def test_config_versionada_confirmada_ao_vivo():
    c = cfg_suim()
    assert c.pendencias() == []
    assert (c.programa, c.coluna_role, c.coluna_tipo) == ("RSUSR070", "AGR_NAME", "TYPE_ICON")
    assert suim.popup_permitido(POPUP_REAL, c.popups_permitidos)
    with pytest.raises(TelaInesperada, match="ainda não confirmada"):
        suim.SuimRoles(object(), cfg_suim(programa=""))


def test_caminho_gravado_roles_e_aviso_de_roles_ocultas():
    c = cfg_suim()
    s = SessaoFalsa(c)
    suim_ = suim.SuimRoles(s, c)
    roles = suim_.roles_por_transacao("FB01")
    assert roles == (RoleSuim("Y-BRA-DEPRECIATION_PROCESSING", TipoRole.SINGLE, "Asset Depreciation Processing"),
                     RoleSuim("Y-BRF-FB01-POST_DOCUMENT", TipoRole.SINGLE, "Post Document"))
    assert s.arvore.expandidos == ["02  1      3", "03  2      1"] and s.arvore.clicados == ["04  2      2"]
    assert s.comps["wnd[0]/tbar[0]/okcd"].text == "/nSUIM"
    assert s.comps[c.campo_objeto].text == "S_TCODE" and s.comps[c.campo_valor].text == "FB01"
    assert s.comps["wnd[0]/tbar[1]/btn[8]"].pressionado == 1 and s.comps["wnd[1]/tbar[0]/btn[0]"].pressionado == 1
    assert any("523 roles" in a for a in suim_.avisos)


def test_singles_da_inspecao_real():
    c = cfg_suim()
    r = suim.SuimRoles(SessaoFalsa(c), c)
    assert r.singles_por_transacao("FB01") == ("Y-BRA-DEPRECIATION_PROCESSING", "Y-BRF-FB01-POST_DOCUMENT")


def test_composites_sao_ignoradas_com_aviso():
    c = cfg_suim()
    s = SessaoFalsa(c, popup=None, linhas=LINHAS_COMPOSITE + LINHAS_REAIS[:1])
    r = suim.SuimRoles(s, c)
    assert r.singles_por_transacao("FB01") == ("Y-BRF-FB01-POST_DOCUMENT",)
    assert len(r.avisos) == 1 and "Z-BRA-COMP, Z-BRF-COMP" in r.avisos[0]
    assert s.comps["wnd[1]/tbar[0]/btn[0]"].pressionado == 0


def test_tipo_desconhecido_para_a_etapa():
    c = cfg_suim()
    s = SessaoFalsa(c, linhas=[{"AGR_NAME": "Y-X", "TYPE_ICON": "@IC@", "AGR_TEXT": ""}])
    with pytest.raises(TelaInesperada, match="não reconhecido"):
        suim.SuimRoles(s, c).singles_por_transacao("FB01")


def test_titulo_diferente_nao_digita():
    c = cfg_suim()
    s = SessaoFalsa(c, titulo="Change Documents for Users")
    with pytest.raises(TelaInesperada, match="SUIM abriu"):
        suim.SuimRoles(s, c).roles_por_transacao("FB01")
    assert s.comps[c.campo_objeto].text == ""


def test_programa_diferente_nao_digita():
    c = cfg_suim()
    s = SessaoFalsa(c, programa="RSUSR100N")
    with pytest.raises(TelaInesperada, match="programa"):
        suim.SuimRoles(s, c).roles_por_transacao("FB01")
    assert s.comps[c.campo_objeto].text == ""


def test_popup_desconhecido_nao_e_confirmado():
    c = cfg_suim()
    s = SessaoFalsa(c, popup="Question | Do you want to save?")
    with pytest.raises(TelaInesperada, match="popup"):
        suim.SuimRoles(s, c).roles_por_transacao("FB01")
    assert s.comps["wnd[1]/tbar[0]/btn[0]"].pressionado == 0


def test_inspecao_sem_conferencias():
    c = cfg_suim()
    s = SessaoFalsa(c, titulo="Outra tela", popup="Qualquer | coisa")
    assert suim.abrir_relatorio(s, c, conferir=False) == "Outra tela"
    popup, _ = suim.executar_busca(s, c, "FB01", conferir=False)
    assert popup == "Qualquer | coisa" and s.comps["wnd[1]/tbar[0]/btn[0]"].pressionado == 1


def test_ler_grade_rola_por_blocos():
    linhas = [{"AGR_NAME": f"R{i}", "TYPE_ICON": "@IC\\QSin", "AGR_TEXT": str(i)} for i in range(5)]
    colunas, lidas = sap_gui.ler_grade(GradeFalsa(linhas, visiveis=2))
    assert colunas == GradeFalsa.TITULOS and lidas == linhas


def test_coluna_ausente_e_tela_diferente():
    with pytest.raises(TelaInesperada, match="coluna"):
        suim.extrair_roles([{"AGR_NAME": "x"}], cfg_suim())
    assert suim.extrair_roles([], cfg_suim()) == ()


@pytest.mark.parametrize("icone,tipo", [("@IC\\QSin", TipoRole.SINGLE), ("@IC\\QSingle Role@", TipoRole.SINGLE),
                                        ("@IC\\QCom", TipoRole.COMPOSITE), ("@IC\\QComposite Role@", TipoRole.COMPOSITE),
                                        ("@IC@", TipoRole.DESCONHECIDO), ("", TipoRole.DESCONHECIDO)])
def test_tipo_do_icone(icone, tipo):
    assert suim.tipo_do_icone(icone) is tipo


def test_roles_ocultas():
    assert suim.roles_ocultas(POPUP_REAL) == 523
    assert suim.roles_ocultas("Information | 1.204 roles with missing authorization not displayed") == 1204
    assert suim.roles_ocultas("Number of hits: 3") is None and suim.roles_ocultas(None) is None
