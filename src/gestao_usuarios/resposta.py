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
    if isinstance(v, int) and not isinstance(v, bool):      # o Forms entrega o Response Id como número
        return str(v)
    return v.strip() if isinstance(v, str) else ""


# O Forms ramifica (seções 'Criação de usuário' e 'Modificação de acesso'). O fluxo do Power Automate grava a resposta crua:
# uma chave por pergunta, com o ID que o Forms deu a ela (docs/forms-e-fluxos.md), mais 'responder', 'submitDate' e 'id_resposta'.
# Os nomes legíveis (criacao_igg, igg...) continuam valendo (testes, reprocessamento e um fluxo que renomeie as chaves).
ID_TIPO = "re72ac6907e2d4cab8bdfd5be73b385db"
CHAVES = {
    Tipo.CRIACAO: {"igg": ("r1b4568cc37574ca3977384e4e5a19dec", "criacao_igg", "igg"),
                   "referencia": ("r886c8288e16e4395b18dd31413a8b751", "criacao_referencia", "usuario_referencia"),
                   "justificativa": ("r4e7aee5435694475a7b383ad319db54b", "criacao_justificativa", "justificativa"),
                   "transacoes": ("criacao_transacoes", "transacoes")},
    Tipo.MODIFICACAO: {"igg": ("rd5822024821e4e7f8b25a2ef94ea40e0", "modificacao_igg", "igg"),
                       "referencia": (),
                       "justificativa": ("r4a2c00f93e374f2aa59595244af7651c", "modificacao_justificativa", "justificativa"),
                       "transacoes": ("rf821d5f8f8604eb78ff9f1796ad0de52", "modificacao_transacoes", "transacoes")},
}


def _primeiro(d: dict, chaves: tuple[str, ...]) -> str:
    for c in chaves:
        v = _texto(d, c)
        if v:
            return v
    return ""


def de_dict(d, arquivo: str) -> Solicitacao:
    if not isinstance(d, dict):
        raise RespostaInvalida("o JSON não é um objeto")
    id_resposta = _texto(d, "id_resposta")
    if not id_resposta:
        raise RespostaInvalida("sem id_resposta")
    tipo = ler_tipo(d.get("tipo") if "tipo" in d else d.get(ID_TIPO))
    k = CHAVES[tipo]
    return Solicitacao(
        arquivo=arquivo,
        id_resposta=id_resposta,
        tipo=tipo,
        igg=_primeiro(d, k["igg"]).upper(),
        transacoes=separar_transacoes(_primeiro(d, k["transacoes"])),
        justificativa=_primeiro(d, k["justificativa"]),
        solicitante_nome=_texto(d, "solicitante_nome"),
        solicitante_email=_primeiro(d, ("solicitante_email", "responder")).lower(),
        usuario_referencia=_primeiro(d, k["referencia"]).upper() or None,
        enviado_em=_primeiro(d, ("enviado_em", "submitDate")) or None,
    )


def ler_resposta(caminho: Path) -> Solicitacao:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RespostaInvalida(f"JSON ilegível: {e}") from e
    return de_dict(dados, caminho.name)
