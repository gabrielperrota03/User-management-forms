"""Guardas de segurança. Funções puras: devolvem a lista de MOTIVOS de recusa (vazia = tudo certo).
Na dúvida a aplicação não age: vira aviso no relatório e um humano decide."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .resposta import Solicitacao, Tipo

RE_IGG = re.compile(r"^[A-Z]\d{7}$")
RE_TRANSACAO = re.compile(r"^[A-Z][A-Z0-9_/]{1,19}$")


@dataclass(frozen=True)
class RegrasSeguranca:
    dominios_permitidos: tuple[str, ...] = ("totalenergies.com", "external.totalenergies.com")
    igg_protegidos: frozenset[str] = frozenset()
    max_transacoes: int = 10

    @classmethod
    def de_config(cls, cfg: dict | None) -> "RegrasSeguranca":
        c = (cfg or {}).get("seguranca") or {}
        d = cls()
        return cls(
            dominios_permitidos=tuple(x.lower() for x in c.get("dominios_permitidos", d.dominios_permitidos)),
            igg_protegidos=frozenset(x.upper() for x in (c.get("igg_protegidos") or ())),
            max_transacoes=int(c.get("max_transacoes", d.max_transacoes)),
        )


def avaliar_solicitacao(s: Solicitacao, r: RegrasSeguranca) -> list[str]:
    motivos: list[str] = []
    usuario, arroba, dominio = s.solicitante_email.rpartition("@")
    if not (usuario and arroba and dominio in r.dominios_permitidos):
        motivos.append(f"solicitante fora dos domínios permitidos: {s.solicitante_email or '(vazio)'}")
    if not RE_IGG.match(s.igg):
        motivos.append(f"IGG com formato inválido: {s.igg!r}")
    elif s.igg in r.igg_protegidos:
        motivos.append(f"IGG {s.igg} é protegido: a aplicação nunca age sobre ele")
    if s.tipo is Tipo.CRIACAO:
        if not s.usuario_referencia:
            motivos.append("criação sem usuário de referência")
        elif not RE_IGG.match(s.usuario_referencia):
            motivos.append(f"usuário de referência com formato inválido: {s.usuario_referencia!r}")
        elif s.usuario_referencia == s.igg:
            motivos.append("usuário de referência igual ao próprio usuário")
    if not s.transacoes:
        if s.tipo is Tipo.MODIFICACAO:                  # na criação o Forms não pede transações (o perfil vem do ZBR da referência)
            motivos.append("nenhuma transação informada")
    elif len(s.transacoes) > r.max_transacoes:
        motivos.append(f"{len(s.transacoes)} transações: o máximo por solicitação é {r.max_transacoes}")
    invalidas = [t for t in s.transacoes if not RE_TRANSACAO.match(t)]
    if invalidas:
        motivos.append(f"transações com formato inválido: {', '.join(invalidas)}")
    if not s.justificativa:
        motivos.append("sem justificativa")
    return motivos
