"""Interfaces com SAP e GRC. Permitem testar o fluxo inteiro sem as ferramentas reais.

As implementações reais (sap_e1p.py, sap_o97.py, grc.py) só leem, exceto `GrcRequest.criar_usuario`.
Cada implementação real guarda os próprios prints para o relatório.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from .analise import Risco
    from .decisao import UsuarioSap


class SapE1P(Protocol):
    def usuario(self, igg: str) -> "UsuarioSap":
        """SU01D (somente leitura): existe? bloqueado?"""

    def singles_por_transacao(self, transacao: str) -> tuple[str, ...]:
        """SUIM › Roles by Complex Selection Criteria, S_TCODE = transação: single roles (somente leitura)."""


class FonteZbr(Protocol):
    def zbrs_de(self, igg: str) -> tuple[str, ...]:
        """O97 › User x Business Roles Report para um IGG (somente leitura)."""


class GrcRisco(Protocol):
    def simular(self, usuario: str, role: str) -> tuple["Risco", ...]:
        """Access Risk Analysis › User Level com simulação do usuário + single role. Nada é salvo no GRC."""


class GrcRequest(Protocol):
    def criar_usuario(self, igg: str, zbr: str, descricao: str, *, submeter: bool = True,
                      verificar: "Callable[[], str | None] | None" = None) -> str | None:
        """Request 'New or Change Account' (usuário novo + business role ZBR). Com submeter=True devolve o número da request
        (só com a mensagem de sucesso); com submeter=False (ensaio) preenche e confere o formulário e devolve None.
        `verificar` roda com o formulário pronto, imediatamente antes do Submit: devolve o motivo de recusa ou None."""
