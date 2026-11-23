"""E1P: porta SapE1P real = SU01D (o usuário existe? está bloqueado?) + SUIM (transação -> single roles). SOMENTE LEITURA.

SU01D portada do lock-users (calibrada ao vivo em 05/11/2026): /nSU01D, User = IGG, Display (F7). Título 'Display Users' =
existe; senão a barra de status diz que não existe. Aba Logon Data: a linha 'User is locked' indica bloqueio; se as seções
conhecidas da aba não foram lidas, o estado de bloqueio é incerto (None) e o relatório avisa.
Usa UMA sessão própria (sap_gui.SessaoPropria) aberta pela rodada; nunca as sessões do analista.
Não tira print da SU01D nem da SUIM (o relatório só leva os do GRC); `tirar_prints=True` liga de volta, para depuração.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from . import sap_gui
from .capturas import capturar_janela_sap
from .decisao import UsuarioSap
from .suim import ConfigSuim, SuimRoles

log = logging.getLogger(__name__)

CAMPO_USUARIO = "wnd[0]/usr/ctxtSUID_ST_BNAME-BNAME"
ABA_LOGON = "wnd[0]/usr/tabsTABSTRIP1/tabpLOGO"
TITULO_EXISTE = "Display Users"
_RE_BLOQUEADO = re.compile(r"user is locked", re.I)
_MARCADORES_ABA_LOGON = ("validity period", "user type", "password status")


def esta_bloqueado(textos: list[str]) -> bool:
    return any(_RE_BLOQUEADO.search(t or "") for t in textos)


def aba_logon_lida(textos: list[str]) -> bool:
    junto = " ".join(textos).lower()
    return any(m in junto for m in _MARCADORES_ABA_LOGON)


def interpretar_logon(textos: list[str]) -> UsuarioSap:
    """Usuário que existe: bloqueado True/False, ou None se a aba não foi lida por inteiro."""
    return UsuarioSap(existe=True, bloqueado=esta_bloqueado(textos) if aba_logon_lida(textos) else None)


class SapE1PReal:
    """Porta SapE1P. `prints` e `avisos` acumulam o que vai para o relatório (a rodada esvazia entre solicitações)."""

    def __init__(self, sessao, c_suim: ConfigSuim, pasta_prints: Path | None = None, tirar_prints: bool = False):
        self.sessao = sessao
        self.suim = SuimRoles(sessao, c_suim)
        self.pasta_prints = pasta_prints
        self.tirar_prints = tirar_prints        # SU01D/SUIM sem print: decisão do analista, 23/11/2026 (só o GRC é evidência)
        self.prints: list[Path] = []

    @property
    def avisos(self) -> list[str]:
        return self.suim.avisos

    def limpar(self, pasta_prints: Path | None) -> None:
        self.pasta_prints, self.prints = pasta_prints, []
        self.suim.avisos.clear()

    def _print(self, nome: str) -> None:
        if self.tirar_prints and self.pasta_prints is not None:
            p = capturar_janela_sap(self.sessao.findById("wnd[0]"), self.pasta_prints / nome)
            if p:
                self.prints.append(p)

    def usuario(self, igg: str) -> UsuarioSap:
        s = self.sessao
        sap_gui.achar(s, "wnd[0]/tbar[0]/okcd").text = "/nSU01D"
        sap_gui.achar(s, "wnd[0]").sendVKey(0)
        sap_gui.esperar(s)
        sap_gui.achar(s, CAMPO_USUARIO).text = igg
        sap_gui.achar(s, "wnd[0]").sendVKey(0)
        sap_gui.esperar(s)
        sap_gui.achar(s, "wnd[0]/tbar[1]/btn[7]").press()          # Display (F7)
        sap_gui.esperar(s)
        if not sap_gui.titulo(s).startswith(TITULO_EXISTE):
            self._print(f"su01d_{igg}_inexistente.png")
            return UsuarioSap(existe=False)
        sap_gui.achar(s, ABA_LOGON).select()
        sap_gui.esperar(s)
        usuario = interpretar_logon(sap_gui.coletar_textos(sap_gui.achar(s, ABA_LOGON), 8))
        self._print(f"su01d_{igg}.png")
        sap_gui.achar(s, "wnd[0]/tbar[0]/btn[3]").press()          # volta para a tela inicial
        sap_gui.esperar(s)
        return usuario

    def singles_por_transacao(self, transacao: str) -> tuple[str, ...]:
        roles = self.suim.singles_por_transacao(transacao)
        self._print(f"suim_{transacao}.png")
        return roles
