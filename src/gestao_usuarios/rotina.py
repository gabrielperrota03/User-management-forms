"""Uma rodada: respostas novas da pasta -> análise -> relatório -> manifesto (docs/ARQUITETURA.md, seções 3 e 4).

As conexões (SAP E1P, GRC, O97) vêm de um objeto `Conexoes` aberto sob demanda: rodada sem resposta nova não toca em nada.
Uma solicitação que falha vira AVISO no relatório e não derruba as outras; SessaoParada (SAP/GRC indisponível, login pedido)
para a rodada inteira e a solicitação fica pendente para a próxima (não entra no manifesto).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from . import relatorio
from .decisao import Acao, AcaoRequest
from .erros import SessaoParada
from .manifesto import Entrada, Fase, Manifesto
from .processador import Opcoes, Resultado, processar
from .resposta import RespostaInvalida, ler_resposta
from .seguranca import RegrasSeguranca
from .zbr import ListaZbr

log = logging.getLogger(__name__)


class Conexoes(Protocol):
    """Portas reais (ou simuladas nos testes), abertas na primeira vez que são pedidas."""

    def sap(self): ...
    def grc_risco(self): ...
    def grc_request(self): ...
    def fonte_zbr(self): ...
    def preparar(self, pasta_prints: Path) -> None: ...     # zera prints/avisos e define onde gravar os prints
    def evidencias(self) -> tuple[list[Path], list[str]]: ...  # (prints, avisos) da solicitação atual
    def fechar(self) -> None: ...


@dataclass
class Resumo:
    arquivo: str
    situacao: str
    relatorio: Path | None = None
    erro: str | None = None


@dataclass
class Saida:
    resumos: list[Resumo] = field(default_factory=list)
    parada: str | None = None                           # motivo da SessaoParada, se a rodada parou

    @property
    def codigo(self) -> int:
        if self.parada:
            return 2
        return 1 if any(r.erro for r in self.resumos) else 0


def novas_respostas(pasta: Path, manifesto: Manifesto) -> list[Path]:
    """JSONs da pasta (e das subpastas MM_AA) ainda não registrados no manifesto, em ordem de nome (= de chegada)."""
    if not pasta.exists():
        return []
    return sorted((p for p in pasta.rglob("*.json") if not manifesto.conhece_arquivo(p.name)), key=lambda p: p.name)


def fase_do_resultado(res: Resultado) -> Fase:
    if res.recusada:
        return Fase.RECUSADA
    if res.acao is not Acao.ANALISAR:
        return Fase.AVISO
    if res.acao_request is AcaoRequest.SIMULAR:
        return Fase.ANALISADA                            # dry-run de criação: volta a rodar com --executar
    if res.acao_request is AcaoRequest.BARRADA_DISJUNTOR:
        return Fase.ANALISADA                            # fica para a próxima rodada
    return Fase.CONCLUIDA


class _PortasPreguicosas:
    """Adia a abertura de cada conexão até o processador realmente usá-la."""

    def __init__(self, c: Conexoes):
        self.c = c

    def usuario(self, igg):
        return self.c.sap().usuario(igg)

    def singles_por_transacao(self, t):
        return self.c.sap().singles_por_transacao(t)

    def simular(self, usuario, role):
        return self.c.grc_risco().simular(usuario, role)

    def criar_usuario(self, igg, zbr, descricao, **opcoes):
        return self.c.grc_request().criar_usuario(igg, zbr, descricao, **opcoes)

    def zbrs_de(self, igg):
        return self.c.fonte_zbr().zbrs_de(igg)


def rodada(arquivos: list[Path], *, manifesto: Manifesto, conexoes: Conexoes, regras: RegrasSeguranca, opcoes: Opcoes,
           pasta_relatorios: Path, pasta_trabalho: Path, lista_zbr: ListaZbr | None, agora: datetime) -> Saida:
    saida = Saida()
    portas = _PortasPreguicosas(conexoes)
    criadas = 0
    for arq in arquivos:
        try:
            s = ler_resposta(arq)
        except RespostaInvalida as e:
            log.warning("%s: resposta inválida (%s)", arq.name, e)
            manifesto.adicionar(Entrada(arq.name, arq.name, Fase.RECUSADA, avisos=[str(e)]))
            manifesto.salvar()
            saida.resumos.append(Resumo(arq.name, "RECUSADA", erro=f"resposta inválida: {e}"))
            continue
        anterior = manifesto.entradas.get(s.id_resposta)
        if anterior is not None and anterior.final:
            log.info("%s: resposta %s já tratada (%s)", arq.name, s.id_resposta, anterior.arquivo)
            continue
        conexoes.preparar(pasta_trabalho / s.id_resposta)
        erro = None
        try:
            res = processar(s, regras=regras, sap=portas, grc_risco=portas, grc_request=portas, lista_zbr=lista_zbr,
                            fonte_zbr=portas, agora=agora, opcoes=opcoes, requests_criadas=criadas)
        except SessaoParada as e:
            log.error("rodada parada em %s: %s", arq.name, e)
            saida.parada = str(e)
            break
        except Exception as e:  # noqa: BLE001 - uma solicitação não derruba as outras
            log.exception("%s: falha na análise", arq.name)
            erro = f"{type(e).__name__}: {e}"
            res = Resultado(s, motivo=f"falha na análise: {erro}")
        prints, avisos = conexoes.evidencias()
        res.avisos += [a for a in avisos if a not in res.avisos]
        if res.request:
            criadas += 1
        caminho = relatorio.gravar(res, prints, pasta_relatorios, datetime.now())
        entrada = anterior or Entrada(s.id_resposta, arq.name)
        entrada.arquivo, entrada.tipo, entrada.igg = arq.name, s.tipo.value, s.igg
        entrada.fase = Fase.AVISO if erro else fase_do_resultado(res)
        entrada.request = res.request or entrada.request
        entrada.conflito = res.comparativo.conflito if res.comparativo else None
        entrada.avisos = list(res.recusa) + list(res.avisos) + ([erro] if erro else [])
        manifesto.entradas[entrada.chave] = entrada
        manifesto.salvar()                                   # tudo ou nada, depois de cada solicitação
        saida.resumos.append(Resumo(arq.name, relatorio.situacao(res), caminho, erro))
    return saida
