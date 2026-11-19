"""Paginação da tabela de resultado do GRC com uma tela falsa no formato real (lsdata e rr, conferidos em 19/11/2026):
tabela '{2:<total>,...,5:<por tela>,...}', barra '{0:<primeira linha>,1:...,10:<total>}', linhas tr[rr] absolutas e rr=0 vazias."""
import pytest

from gestao_usuarios import wd
from gestao_usuarios.sap_gui import TelaInesperada

COLUNAS = ["User ID", "Access Risk ID", "Risk Level", "Action"]


def linha(i):
    return {"User ID": "L1170904", "Access Risk ID": f"R{i:03d}", "Risk Level": "Critical", "Action": f"T{i}"}


class Caixa:
    def bounding_box(self):
        return {"x": 10, "y": 300, "width": 1000, "height": 180}


class FrameFalso:
    """Mostra `por_tela` linhas a partir de `posicao`; a roda do mouse anda `passo` linhas (ou trava, se passo=0)."""

    def __init__(self, total, por_tela=10, passo=9, pular=()):
        self.total, self.por_tela, self.passo, self.pular = total, por_tela, passo, set(pular)
        self.posicao = 1

    def evaluate(self, js, cabecalho):
        fim = min(self.posicao + self.por_tela - 1, self.total)
        linhas = {str(i): linha(i) for i in range(self.posicao, fim + 1) if i not in self.pular}
        return {"id": "WD05C8", "colunas": COLUNAS, "linhas": linhas,
                "lsdata": f"{{2:{self.total},3:19,4:1,5:{self.por_tela},6:19}}",
                "barra": f"{{0:{self.posicao},1:-{self.total},2:1,6:'WD05C8',10:{self.total}}}"}

    def locator(self, _):
        return Caixa()

    def rolar(self, para_baixo=True):
        nova = self.posicao + (self.passo if para_baixo else -self.passo)
        self.posicao = max(1, min(nova, max(self.total - self.por_tela + 1, 1)))


class Mouse:
    def __init__(self, frame):
        self.frame = frame

    def move(self, x, y):
        pass

    def wheel(self, dx, dy):
        self.frame.rolar(dy > 0)


class PaginaFalsa:
    def __init__(self, frame):
        self.mouse = Mouse(frame)

    def wait_for_timeout(self, ms):
        pass


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(wd, "aguardar", lambda *a, **k: None)


def telas_esperadas(total, por_tela=10):
    """Uma tela por bloco de linhas novas: 1..10, 11..20, ...; a última encosta no fim."""
    return max(1, -(-total // por_tela))


@pytest.mark.parametrize("passo", [1, 3, 9])           # ao vivo: 1 linha por giro
@pytest.mark.parametrize("total", [0, 1, 8, 10, 11, 23, 57, 139])
def test_le_todas_as_linhas_na_ordem_com_poucas_telas(total, passo):
    f = FrameFalso(total, passo=passo)
    telas = []
    t = wd.ler_tabela(PaginaFalsa(f), f, "Access Risk ID", ao_mostrar=telas.append)
    assert t["total"] == total and t["linhas"] == [linha(i) for i in range(1, total + 1)]
    if passo == 1:                                        # o caso real: uma tela por bloco de 10 linhas novas
        assert len(telas) <= telas_esperadas(total), f"{len(telas)} telas para {total} linhas"
    else:                                                 # giro maior: volta até a linha que falta, sem pular nenhuma
        assert len(telas) <= max(1, total)


def test_tabela_que_nao_rola_nao_finge_que_leu():
    f = FrameFalso(15, passo=0)
    with pytest.raises(TelaInesperada, match="não rolou"):
        wd.ler_tabela(PaginaFalsa(f), f, "Access Risk ID")


def test_linha_que_nunca_aparece_e_erro():
    f = FrameFalso(12, pular={11})
    with pytest.raises(TelaInesperada, match=r"\[11\]|não rolou"):
        wd.ler_tabela(PaginaFalsa(f), f, "Access Risk ID")


def test_info_e_linhas_faltando():
    bruto = {"lsdata": "{2:8,3:19,4:1,5:10,6:19}", "barra": "{0:1,1:-1,2:1,6:'WD05C8',10:8}"}
    assert wd.info_tabela(bruto) == {"total": 8, "por_tela": 10, "posicao": 1}
    assert wd.info_tabela({"lsdata": "", "barra": ""}) == {"total": None, "por_tela": None, "posicao": None}
    assert wd.linhas_faltando({1, 2, 4}, 5) == [3, 5] and wd.linhas_faltando(["1"], 1) == []
