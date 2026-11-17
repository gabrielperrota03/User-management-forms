"""Estado de cada solicitação, em JSON. Chave = id da resposta do Forms (o mesmo envio nunca é tratado duas vezes)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

from .arquivos import gravar_texto


class Fase(StrEnum):
    NOVA = "nova"
    RECUSADA = "recusada"          # guardas de segurança (final)
    AVISO = "aviso"                # um humano decide (final)
    ANALISADA = "analisada"
    REQUEST_CRIADA = "request_criada"
    CONCLUIDA = "concluida"        # relatório gravado (final)


FASES_FINAIS = frozenset({Fase.RECUSADA, Fase.AVISO, Fase.CONCLUIDA})


@dataclass
class Entrada:
    chave: str
    arquivo: str
    fase: Fase = Fase.NOVA
    tipo: str | None = None
    igg: str | None = None
    request: str | None = None
    conflito: bool | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def final(self) -> bool:
        return self.fase in FASES_FINAIS

    def to_json(self) -> dict:
        return {**asdict(self), "fase": self.fase.value}

    @classmethod
    def from_json(cls, d: dict) -> "Entrada":
        return cls(**{**d, "fase": Fase(d["fase"])})


class Manifesto:
    def __init__(self, caminho: Path):
        self.caminho = caminho
        self.entradas: dict[str, Entrada] = {}
        if caminho.exists():
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            self.entradas = {k: Entrada.from_json(v) for k, v in dados.items()}

    def salvar(self) -> None:
        gravar_texto(self.caminho, json.dumps({k: v.to_json() for k, v in self.entradas.items()},
                                              ensure_ascii=False, indent=2))

    def conhece_arquivo(self, arquivo: str) -> bool:
        return any(e.arquivo == arquivo for e in self.entradas.values())

    def adicionar(self, e: Entrada) -> bool:
        if e.chave in self.entradas:
            return False
        self.entradas[e.chave] = e
        return True

    def pendentes(self) -> list[Entrada]:
        return [e for e in self.entradas.values() if not e.final]
