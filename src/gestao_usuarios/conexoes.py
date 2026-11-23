"""Conexões reais da rodada, abertas na primeira vez que são pedidas e fechadas no fim.

- E1P: uma sessão PRÓPRIA (sap_gui.SessaoPropria), SU01D + SUIM (sap_e1p.SapE1PReal).
- GRC: Chromium dedicado por CDP (aberto se estiver fechado, padrão do lock-users); a aba do NWBC é recarregada uma vez
  para renovar a sessão (o SSO reautentica sozinho). Login pedido ou sessão vencida = SessaoParada (o analista entra).
- O97: FonteZbrO97 abre e fecha a própria sessão a cada consulta.
- Request de criação: ainda não implementada (grc_request.py); pedir para criar levanta erro (vira AVISO no relatório).
"""
from __future__ import annotations

import logging
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from . import sap_gui
from .erros import SessaoParada
from .grc_risco import ConfigGrcRisco, GrcRiscoPlaywright
from .sap_e1p import SapE1PReal
from .sap_o97 import ConfigO97, FonteZbrO97
from .suim import ConfigSuim

log = logging.getLogger(__name__)


def porta_aberta(cdp: str, timeout: float = 1.0) -> bool:
    u = urlparse(cdp)
    try:
        with socket.create_connection((u.hostname, u.port), timeout=timeout):
            return True
    except OSError:
        return False


def garantir_navegador(cdp: str, chrome: str, perfil: str, espera: float = 30.0) -> None:
    """Sobe o Chromium dedicado (perfil próprio, depuração só local) se a porta CDP estiver fechada. Não faz login."""
    if porta_aberta(cdp):
        return
    if not chrome or not Path(chrome).exists():
        raise SessaoParada(f"Chromium dedicado fechado e executável não encontrado ({chrome!r})")
    log.info("Chromium dedicado fechado; abrindo (%s)", chrome)
    subprocess.Popen(
        [chrome, f"--user-data-dir={perfil}", f"--remote-debugging-port={urlparse(cdp).port}",
         "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check", "about:blank"],
        creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        if porta_aberta(cdp):
            return
        time.sleep(0.5)
    raise SessaoParada("o Chromium dedicado não abriu a porta de depuração")


def _sessao_grc_expirada(pagina) -> bool:
    if "login." in pagina.url.split("/")[2]:
        return True
    for f in pagina.frames:
        try:
            t = f.evaluate("document.body ? document.body.innerText : ''")
        except Exception:  # noqa: BLE001
            continue
        if "Unauthorized Error" in t or "session has expired" in t.lower():
            return True
    return False


class GrcRequestPendente:
    def criar_usuario(self, igg, zbr, descricao):
        raise NotImplementedError("a request de criação no GRC ainda não foi implementada")


class ConexoesReais:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._sessao_sap = None
        self._sap = None
        self._pw = None
        self._grc = None
        self._o97 = None
        self._falha_grc: str | None = None
        self._pasta: Path | None = None

    # --- portas --------------------------------------------------------------------------------------------------
    def sap(self) -> SapE1PReal:
        if self._sap is None:
            self._sessao_sap = sap_gui.SessaoPropria("E1P", self.cfg["sap"]["conexao_e1p"])
            sessao = self._sessao_sap.__enter__()
            self._sap = SapE1PReal(sessao, ConfigSuim.de_config(self.cfg), self._pasta)
        return self._sap

    def grc_risco(self) -> GrcRiscoPlaywright:
        if self._grc is None:
            if self._falha_grc:                                         # já falhou nesta rodada: não tenta de novo
                raise SessaoParada(self._falha_grc)
            try:
                self._grc = self._abrir_grc()
            except SessaoParada as e:
                self._falha_grc = str(e)
                raise
            except Exception as e:  # noqa: BLE001 - qualquer falha ao conectar = GRC indisponível nesta rodada
                self._falha_grc = f"GRC indisponível ({type(e).__name__}: {str(e).splitlines()[0][:200]})"
                raise SessaoParada(self._falha_grc) from e
        return self._grc

    def _abrir_grc(self) -> GrcRiscoPlaywright:
        from playwright.sync_api import sync_playwright

        g = self.cfg["grc"]
        garantir_navegador(g["cdp"], g.get("chrome", ""), g.get("perfil", ""))
        if self._pw is None:                                            # o Playwright sync só pode ser aberto uma vez
            self._pw = sync_playwright().start()
        contexto = self._pw.chromium.connect_over_cdp(g["cdp"], timeout=60000).contexts[0]
        home = next((p for p in contexto.pages if "/ui2/nwbc/" in p.url), None) or contexto.new_page()
        home.goto(g["url"], wait_until="load", timeout=60000)          # renova a sessão (SSO)
        home.wait_for_timeout(5000)
        if _sessao_grc_expirada(home):
            raise SessaoParada("sessão do GRC expirada: entre na janela do Chromium dedicado e rode de novo")
        return GrcRiscoPlaywright(contexto, ConfigGrcRisco.de_config(self.cfg), self._pasta)

    def grc_request(self):
        return GrcRequestPendente()

    def fonte_zbr(self) -> FonteZbrO97:
        if self._o97 is None:
            self._o97 = FonteZbrO97(ConfigO97.de_config(self.cfg))
        return self._o97

    # --- evidências ----------------------------------------------------------------------------------------------
    def preparar(self, pasta_prints: Path) -> None:
        self._pasta = pasta_prints
        if self._sap is not None:
            self._sap.limpar(pasta_prints)
        if self._grc is not None:
            self._grc.pasta_prints, self._grc.prints = pasta_prints, []

    def evidencias(self) -> tuple[list[Path], list[str]]:
        prints = (self._sap.prints if self._sap else []) + (self._grc.prints if self._grc else [])
        avisos = list(self._sap.avisos) if self._sap else []
        return prints, avisos

    def fechar(self) -> None:
        if self._sessao_sap is not None:
            self._sessao_sap.__exit__(None, None, None)
        if self._pw is not None:
            try:
                self._pw.stop()                                         # desconecta; o Chromium continua aberto
            except Exception:  # noqa: BLE001
                pass
