"""E1P por RFC: a SU01D da criação (o usuário existe?) sem tela, com `BAPI_USER_GET_DETAIL`. SOMENTE LEITURA.

Substitui `SapE1PReal.usuario` (SAP GUI Scripting) quando `sap.modo_usuario: rfc`; o resultado é o mesmo `UsuarioSap`.
Mensagem de usuário inexistente vista ao vivo (E1M, 25/11/2026): RETURN TYPE=E, ID=01, NUMBER=124. Qualquer outro erro = leitura
incerta (`existe=None`), nunca "não existe" (regra 4). Falha ao conectar para a rodada (SessaoParada), como o SAP GUI indisponível.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .decisao import UsuarioSap
from .erros import SessaoParada
from .rfc_sap import ErroRFC, Rfc, conectar_por_sistema

log = logging.getLogger(__name__)

NAO_EXISTE = ("01", "124")                           # (ID, NUMBER) do RETURN de BAPI_USER_GET_DETAIL: "User & does not exist"


def interpretar_detalhe(retorno: list[dict[str, str]], bloqueios: dict[str, str] | None) -> UsuarioSap:
    """RETURN + ISLOCKED -> UsuarioSap. Erro de 'não existe' = existe False; outro erro/aviso grave = incerto; sem erro = existe."""
    erros = [r for r in retorno if r.get("TYPE") in ("E", "A")]
    if erros:
        if any((r.get("ID", ""), r.get("NUMBER", "")) == NAO_EXISTE for r in erros):
            return UsuarioSap(existe=False)
        return UsuarioSap(existe=None)
    if bloqueios is None:
        return UsuarioSap(existe=True, bloqueado=None)
    return UsuarioSap(existe=True, bloqueado=bloqueios.get("LOCAL_LOCK") == "L" or bloqueios.get("GLOB_LOCK") == "L")


class SapE1PRfc:
    """Porta SapE1P só com `usuario()`. As roles vêm do índice (conexoes.roles()). Mesma interface de evidências da SapE1PReal."""

    def __init__(self, sistema: str = "E1P", mandante: str = "010", abrir=None):
        self.sistema, self.mandante = sistema, mandante
        self._abrir = abrir or (lambda: conectar_por_sistema(sistema, mandante)[0])
        self._rfc: Rfc | None = None
        self.prints: list[Path] = []                  # sem prints: o RFC devolve dados, não tela
        self.avisos: list[str] = []

    def limpar(self, pasta_prints: Path | None) -> None:
        self.prints = []
        self.avisos.clear()

    def _conexao(self) -> Rfc:
        if self._rfc is None:
            try:
                self._rfc = self._abrir()
            except ErroRFC as e:
                raise SessaoParada(f"RFC do {self.sistema} indisponível: {e}") from e
        return self._rfc

    def usuario(self, igg: str) -> UsuarioSap:
        rfc = self._conexao()
        try:
            f = rfc.chamar("BAPI_USER_GET_DETAIL", {"USERNAME": igg.strip().upper()})
            try:
                retorno = rfc.tabela(f, "RETURN", ["TYPE", "ID", "NUMBER", "MESSAGE"])
                bloqueios = None
                if not any(r["TYPE"] in ("E", "A") for r in retorno):
                    bloqueios = rfc.estrutura(f, "ISLOCKED", ["LOCAL_LOCK", "GLOB_LOCK"])
            finally:
                rfc.destruir(f)
        except ErroRFC as e:
            log.warning("RFC: leitura de %s falhou (%s)", igg, e)
            self.avisos.append(f"RFC: não deu para ler {igg} no {self.sistema}: {e}")
            self.fechar()                             # a próxima leitura reconecta
            return UsuarioSap(existe=None)
        return interpretar_detalhe(retorno, bloqueios)

    def fechar(self) -> None:
        if self._rfc is not None:
            try:
                self._rfc.fechar()
            except Exception:  # noqa: BLE001
                pass
            self._rfc = None
