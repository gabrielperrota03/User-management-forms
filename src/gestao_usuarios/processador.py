"""Uma solicitação do começo ao fim, pelas portas (docs/ARQUITETURA.md, seção 4)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from .analise import Comparativo, ResultadoComposite, comparar
from .decisao import Acao, AcaoRequest, UsuarioSap, alvo_da_simulacao, decidir_entrada, decidir_request
from .erros import SessaoParada
from .portas import FonteZbr, GrcRequest, GrcRisco, SapE1P
from .resposta import Solicitacao, Tipo
from .seguranca import RegrasSeguranca, avaliar_solicitacao
from .zbr import ListaZbr, resolver_zbr

log = logging.getLogger(__name__)


@dataclass
class Opcoes:
    executar: bool = False                 # dry-run é o padrão
    max_requests: int = 3
    bloquear_com_conflito: bool = True
    zbr_idade_max_dias: float = 8
    zbr_prefixo: str = "ZBR"


@dataclass
class Resultado:
    solicitacao: Solicitacao
    recusa: list[str] = field(default_factory=list)
    acao: Acao | None = None
    motivo: str = ""
    usuario: UsuarioSap | None = None
    zbr: str | None = None
    alvo_simulacao: str | None = None
    comparativo: Comparativo | None = None
    acao_request: AcaoRequest = AcaoRequest.NAO_SE_APLICA
    request: str | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def recusada(self) -> bool:
        return bool(self.recusa)


def processar(s: Solicitacao, *, regras: RegrasSeguranca, sap: SapE1P, grc_risco: GrcRisco, grc_request: GrcRequest,
              lista_zbr: ListaZbr | None, fonte_zbr: FonteZbr | None, agora: datetime, opcoes: Opcoes,
              requests_criadas: int = 0) -> Resultado:
    """Erros de sessão (SessaoParada) sobem: a rodada para e a solicitação é retomada depois."""
    res = Resultado(s)
    res.recusa = avaliar_solicitacao(s, regras)
    if res.recusa:
        return res

    res.usuario = sap.usuario(s.igg)
    referencia = zbrs = None
    if s.tipo is Tipo.CRIACAO and res.usuario.existe is False:
        referencia = sap.usuario(s.usuario_referencia)
        if referencia.existe:
            zbrs = resolver_zbr(s.usuario_referencia, lista_zbr, fonte_zbr, agora,
                                opcoes.zbr_idade_max_dias, opcoes.zbr_prefixo)
    res.acao, res.motivo = decidir_entrada(s, res.usuario, referencia, zbrs)
    if res.acao is not Acao.ANALISAR:
        return res
    if s.tipo is Tipo.CRIACAO:
        res.zbr = zbrs[0]
    if s.tipo is Tipo.MODIFICACAO and res.usuario.bloqueado:
        res.avisos.append(f"{s.igg} está bloqueado no E1P")

    res.alvo_simulacao = alvo_da_simulacao(s)
    resultados: list[ResultadoComposite] = []
    for t in s.transacoes:
        for c in sap.composites_por_transacao(t):
            try:
                resultados.append(ResultadoComposite(t, c, tuple(grc_risco.simular(res.alvo_simulacao, c))))
            except SessaoParada:
                raise
            except Exception as e:  # noqa: BLE001 - uma simulação que falha não derruba as outras, mas não vale "sem risco"
                log.exception("simulação de %s em %s falhou", c, res.alvo_simulacao)
                resultados.append(ResultadoComposite(t, c, erro=str(e) or type(e).__name__))
    res.comparativo = comparar(s.transacoes, resultados)
    for t in res.comparativo.sem_role:
        res.avisos.append(f"nenhuma composite role dá acesso a {t}")
    if not res.comparativo.completo:
        res.avisos.append("alguma simulação falhou: análise incompleta")

    if s.tipo is Tipo.CRIACAO:
        antes_do_submit = sap.usuario(s.igg)            # relido: alguém pode ter criado o usuário nesse meio tempo
        res.acao_request = decidir_request(
            s, antes_do_submit, conflito=res.comparativo.conflito, analise_completa=res.comparativo.completo,
            bloquear_com_conflito=opcoes.bloquear_com_conflito, executar=opcoes.executar,
            requests_criadas=requests_criadas, max_requests=opcoes.max_requests)
        if res.acao_request is AcaoRequest.CRIAR:
            descricao = f"Criação de usuário {s.igg} (ZBR {res.zbr}) - Forms {s.id_resposta}"
            res.request = grc_request.criar_usuario(s.igg, res.zbr, descricao)
    return res
