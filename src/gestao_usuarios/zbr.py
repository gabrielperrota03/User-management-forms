"""Lista semanal de usuários ativos e seus ZBRs (O97, 'User x Business Roles Report'). docs/ARQUITETURA.md, seção 6.

O ZBR não é legível no E1P. A lista evita entrar no O97 a cada solicitação; o O97 só é consultado para um IGG que não está na
lista ou quando a lista ficou velha demais.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .arquivos import gravar_texto
from .portas import FonteZbr


@dataclass
class ListaZbr:
    gerado_em: datetime
    usuarios: dict[str, tuple[str, ...]]

    @classmethod
    def carregar(cls, caminho: Path) -> "ListaZbr | None":
        if not caminho.exists():
            return None
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return cls(datetime.fromisoformat(dados["gerado_em"]),
                   {k.upper(): tuple(v) for k, v in dados["usuarios"].items()})

    def salvar(self, caminho: Path) -> None:
        dados = {"gerado_em": self.gerado_em.isoformat(timespec="seconds"),
                 "usuarios": {k: list(v) for k, v in sorted(self.usuarios.items())}}
        gravar_texto(caminho, json.dumps(dados, ensure_ascii=False, indent=1))

    def idade_dias(self, agora: datetime) -> float:
        return (agora - self.gerado_em).total_seconds() / 86400


def filtrar_zbr(roles, prefixo: str = "ZBR") -> tuple[str, ...]:
    """Do report saem business roles; só as do prefixo contam, sem repetição e em ordem."""
    return tuple(sorted({r.strip().upper() for r in roles if r and r.strip().upper().startswith(prefixo.upper())}))


def resolver_zbr(igg: str, lista: ListaZbr | None, fonte: FonteZbr | None, agora: datetime,
                 idade_max_dias: float = 8, prefixo: str = "ZBR") -> tuple[str, ...] | None:
    """ZBRs do IGG. Lista recente com o IGG = resposta da lista; senão consulta o O97 para o IGG (se houver fonte).
    None = não foi possível saber (vira aviso, nunca chute)."""
    igg = igg.upper()
    if lista is not None and lista.idade_dias(agora) <= idade_max_dias and igg in lista.usuarios:
        return filtrar_zbr(lista.usuarios[igg], prefixo)
    if fonte is None:
        return None
    return filtrar_zbr(fonte.zbrs_de(igg), prefixo)
