"""SAP GUI Scripting: sessão própria e leitura de componentes. SOMENTE LEITURA.

Sessão própria (padrão do lock-users e do sox-automation): cria uma sessão nova na conexão do sistema pedido e fecha só ela,
nunca a última da conexão e nunca as sessões do analista. Credencial nunca é digitada: SAP pedindo login = SessaoParada.
A conexão é escolhida pelo sistema (Info.SystemName), não pela posição: o analista pode ter o O97 e o E1P abertos.
"""
from __future__ import annotations

import logging
import time

from .erros import SessaoParada

log = logging.getLogger(__name__)


class TelaInesperada(RuntimeError):
    """A tela não é a esperada: a automação não segue no escuro."""


def esperar(sessao, limite_s: float = 120) -> None:
    fim = time.monotonic() + limite_s
    while sessao.Busy:
        if time.monotonic() > fim:
            raise TelaInesperada("o SAP continuou ocupado além do limite")
        time.sleep(0.1)


def achar(sessao, id_: str):
    try:
        return sessao.findById(id_)
    except Exception as e:  # noqa: BLE001 - o COM devolve erro genérico
        raise TelaInesperada(f"componente {id_!r} não encontrado na tela {titulo(sessao)!r}") from e


def titulo(sessao, janela: str = "wnd[0]") -> str:
    try:
        return str(sessao.findById(janela).Text)
    except Exception:  # noqa: BLE001
        return ""


def coletar_textos(componente, profundidade: int = 6) -> list[str]:
    textos: list[str] = []
    try:
        v = componente.Text
        if isinstance(v, str) and v.strip():
            textos.append(v.strip())
    except Exception:  # noqa: BLE001
        pass
    if profundidade > 0:
        try:
            filhos = componente.Children
            for i in range(filhos.Count):
                textos += coletar_textos(filhos.Item(i), profundidade - 1)
        except Exception:  # noqa: BLE001
            pass
    return textos


def texto_do_popup(sessao) -> str | None:
    """Texto do popup wnd[1] (título + rótulos), ou None se não há popup."""
    try:
        janela = sessao.findById("wnd[1]")
    except Exception:  # noqa: BLE001
        return None
    return " | ".join([str(janela.Text)] + coletar_textos(janela.findById("usr")))


def ler_grade(grade) -> tuple[dict[str, str], list[dict[str, str]]]:
    """ALV (GuiGridView) -> ({coluna: título exibido}, [linhas como {coluna: valor}]).
    Rola a grade por blocos: o ALV só carrega as linhas que passaram pela tela."""
    colunas = {}
    for i in range(grade.ColumnOrder.Count):
        nome = str(grade.ColumnOrder.Item(i))
        try:
            colunas[nome] = str(grade.GetDisplayedColumnTitle(nome))
        except Exception:  # noqa: BLE001
            colunas[nome] = nome
    total = int(grade.RowCount)
    passo = max(int(getattr(grade, "VisibleRowCount", 0) or 0), 1)
    linhas = []
    for inicio in range(0, total, passo):
        try:
            grade.firstVisibleRow = inicio
        except Exception:  # noqa: BLE001 - grade de uma página só
            pass
        for r in range(inicio, min(inicio + passo, total)):
            linhas.append({c: str(grade.GetCellValue(r, c)).strip() for c in colunas})
    return colunas, linhas


def _conexao_do_sistema(motor, sistema: str):
    for i in range(motor.Children.Count):
        con = motor.Children(i)
        try:
            if con.Children.Count and str(con.Children(0).Info.SystemName).upper() == sistema.upper():
                return con
        except Exception:  # noqa: BLE001
            continue
    return None


class SessaoPropria:
    """`with SessaoPropria('E1P', 'entrada do SAP Logon') as s:` -> sessão nova, fechada na saída."""

    def __init__(self, sistema: str, entrada_logon: str | None = None, limite_s: float = 30):
        self.sistema = sistema
        self.entrada_logon = entrada_logon
        self.limite_s = limite_s
        self._conexao = None
        self.sessao = None
        self._id = None

    def __enter__(self):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            motor = win32com.client.GetObject("SAPGUI").GetScriptingEngine
        except Exception as e:  # noqa: BLE001
            raise SessaoParada("SAP Logon fechado ou Scripting desabilitado") from e
        con = _conexao_do_sistema(motor, self.sistema)
        if con is None:
            if not self.entrada_logon:
                raise SessaoParada(f"nenhuma conexão aberta com {self.sistema} e nenhuma entrada do SAP Logon configurada")
            motor.OpenConnection(self.entrada_logon, False)          # assíncrono: login com SSO, sem credencial
            fim = time.monotonic() + 90
            while (con := _conexao_do_sistema(motor, self.sistema)) is None and time.monotonic() < fim:
                time.sleep(0.5)
            if con is None:
                raise SessaoParada(f"{self.sistema} não abriu em 90 s (login pendente?)")
        antes = {str(con.Children(i).Id) for i in range(con.Children.Count)}
        con.Children(0).createSession()
        fim = time.monotonic() + self.limite_s
        while time.monotonic() < fim:
            for i in range(con.Children.Count):
                s = con.Children(i)
                if str(s.Id) not in antes:
                    self._conexao, self.sessao, self._id = con, s, str(s.Id)
                    if not s.Info.User:
                        self.__exit__()
                        raise SessaoParada(f"{self.sistema} pediu login: entre no SAP e tente de novo")
                    esperar(s)
                    return s
            time.sleep(0.5)
        raise SessaoParada(f"a sessão nova no {self.sistema} não abriu (limite de ~6 sessões por conexão?)")

    def __exit__(self, *exc) -> None:
        if self._id and self._conexao is not None and self._conexao.Children.Count > 1:
            try:
                self._conexao.CloseSession(self._id)
            except Exception:  # noqa: BLE001
                log.warning("não consegui fechar a sessão %s", self._id)
        self.sessao = self._id = None
