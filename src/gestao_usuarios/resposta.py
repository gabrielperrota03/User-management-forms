"""Resposta do Forms gravada pelo Power Automate (um JSON por resposta; formato em docs/forms-e-fluxos.md)."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Tipo(StrEnum):
    CRIACAO = "criacao"
    MODIFICACAO = "modificacao"


class RespostaInvalida(ValueError):
    """JSON ilegível ou sem os campos obrigatórios: a solicitação é recusada."""


@dataclass(frozen=True)
class Solicitacao:
    arquivo: str
    id_resposta: str
    tipo: Tipo
    igg: str
    transacoes: tuple[str, ...]
    justificativa: str
    solicitante_nome: str = ""
    solicitante_email: str = ""
    usuario_referencia: str | None = None
    enviado_em: str | None = None


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def ler_tipo(texto) -> Tipo:
    t = _sem_acento(texto if isinstance(texto, str) else "").strip().lower()
    if t.startswith("cria"):
        return Tipo.CRIACAO
    if t.startswith("modif"):
        return Tipo.MODIFICACAO
    raise RespostaInvalida(f"tipo de solicitação desconhecido: {texto!r}")


def separar_transacoes(texto) -> tuple[str, ...]:
    """'fb01, FB02;fb01' + quebras de linha -> ('FB01', 'FB02'): maiúsculas, sem repetição, na ordem em que vieram."""
    vistas: list[str] = []
    for parte in re.split(r"[,;\s]+", (texto if isinstance(texto, str) else "").upper()):
        if parte and parte not in vistas:
            vistas.append(parte)
    return tuple(vistas)


def _texto(d: dict, chave: str) -> str:
    v = d.get(chave)
    return v.strip() if isinstance(v, str) else ""


def de_dict(d, arquivo: str) -> Solicitacao:
    if not isinstance(d, dict):
        raise RespostaInvalida("o JSON não é um objeto")
    id_resposta = _texto(d, "id_resposta")
    if not id_resposta:
        raise RespostaInvalida("sem id_resposta")
    tipo = ler_tipo(d.get("tipo"))
    referencia = _texto(d, "usuario_referencia").upper() or None
    return Solicitacao(
        arquivo=arquivo,
        id_resposta=id_resposta,
        tipo=tipo,
        igg=_texto(d, "igg").upper(),
        transacoes=separar_transacoes(d.get("transacoes")),
        justificativa=_texto(d, "justificativa"),
        solicitante_nome=_texto(d, "solicitante_nome"),
        solicitante_email=_texto(d, "solicitante_email").lower(),
        usuario_referencia=referencia if tipo is Tipo.CRIACAO else None,
        enviado_em=_texto(d, "enviado_em") or None,
    )


def ler_resposta(caminho: Path) -> Solicitacao:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RespostaInvalida(f"JSON ilegível: {e}") from e
    return de_dict(dados, caminho.name)
