"""Comparação das single roles candidatas (docs/ARQUITETURA.md, seção 5). Funções puras.

Conflito = qualquer risco, em qualquer nível. Nível desconhecido conta como o mais grave (falha para o lado seguro).
Simulação que falhou não é "sem risco": deixa a análise incompleta, e a request de criação não sai.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NIVEIS = ("Critical", "High", "Medium", "Low")


def normalizar_nivel(nivel: str) -> str:
    n = (nivel or "").strip().capitalize()
    return n if n in NIVEIS else "Critical"


@dataclass(frozen=True)
class Risco:
    id: str
    descricao: str
    nivel: str


@dataclass(frozen=True)
class ResultadoRole:
    transacao: str
    role: str
    riscos: tuple[Risco, ...] = ()
    erro: str | None = None

    def contagem(self) -> dict[str, int]:
        c = dict.fromkeys(NIVEIS, 0)
        for r in self.riscos:
            c[normalizar_nivel(r.nivel)] += 1
        return c

    @property
    def nivel_mais_grave(self) -> str | None:
        niveis = {normalizar_nivel(r.nivel) for r in self.riscos}
        return next((n for n in NIVEIS if n in niveis), None)

    def chave_ordem(self) -> tuple:
        c = self.contagem()
        # erro vai para o fim: sem resultado, não pode ser recomendada
        return (self.erro is not None, *(c[n] for n in NIVEIS), len(self.riscos), self.role)


@dataclass
class Comparativo:
    por_transacao: dict[str, list[ResultadoRole]] = field(default_factory=dict)

    @property
    def sem_role(self) -> list[str]:
        return [t for t, lista in self.por_transacao.items() if not lista]

    @property
    def conflito(self) -> bool:
        return any(r.riscos for lista in self.por_transacao.values() for r in lista)

    @property
    def completo(self) -> bool:
        return not any(r.erro for lista in self.por_transacao.values() for r in lista)

    def recomendada(self, transacao: str) -> ResultadoRole | None:
        lista = [r for r in self.por_transacao.get(transacao, []) if r.erro is None]
        return lista[0] if lista else None


def comparar(transacoes: tuple[str, ...], resultados: list[ResultadoRole]) -> Comparativo:
    """Agrupa por transação (na ordem pedida) e ordena as candidatas da menos para a mais arriscada."""
    comp = Comparativo({t: [] for t in transacoes})
    for r in resultados:
        comp.por_transacao.setdefault(r.transacao, []).append(r)
    for lista in comp.por_transacao.values():
        lista.sort(key=ResultadoRole.chave_ordem)
    return comp
