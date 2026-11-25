"""Uma solicitação do começo ao fim, pelas portas (docs/ARQUITETURA.md, seção 4)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from .analise import Comparativo, ResultadoRole, comparar
from .decisao import Acao, AcaoRequest, UsuarioSap, alvo_da_simulacao, decidir_entrada, decidir_request
from .erros import ErroValidacaoGrc, RequestBarrada, SessaoParada, SubmitSemConfirmacao
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
    sem_analise: bool = False              # criação sem transações pedidas: não há o que simular

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

    referencia = zbrs = None
    if s.tipo is Tipo.CRIACAO:                          # modificação não confere o usuário no E1P: a análise de risco basta
        res.usuario = sap.usuario(s.igg)
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

    res.alvo_simulacao = alvo_da_simulacao(s)
    if not s.transacoes:                                # criação: o Forms não pede transações, o perfil é o ZBR da referência
        res.sem_analise = True
        return _fechar_sem_analise(res, s, sap, grc_request, opcoes, requests_criadas)
    resultados: list[ResultadoRole] = []
    for t in s.transacoes:
        for c in sap.singles_por_transacao(t):
            try:
                resultados.append(ResultadoRole(t, c, tuple(grc_risco.simular(res.alvo_simulacao, c))))
            except SessaoParada:
                raise
            except Exception as e:  # noqa: BLE001 - uma simulação que falha não derruba as outras, mas não vale "sem risco"
                log.exception("simulação de %s em %s falhou", c, res.alvo_simulacao)
                resultados.append(ResultadoRole(t, c, erro=str(e) or type(e).__name__))
    res.comparativo = comparar(s.transacoes, resultados)
    for t in res.comparativo.sem_role:
        res.avisos.append(f"nenhuma single role dá acesso a {t}")
    if not res.comparativo.completo:
        res.avisos.append("alguma simulação falhou: análise incompleta")

    if s.tipo is Tipo.CRIACAO:
        _decidir_e_criar(res, s, sap, grc_request, opcoes, requests_criadas,
                         conflito=res.comparativo.conflito, completa=res.comparativo.completo)
    return res


def _fechar_sem_analise(res: Resultado, s: Solicitacao, sap: SapE1P, grc_request: GrcRequest, opcoes: Opcoes,
                        requests_criadas: int) -> Resultado:
    """Criação sem transações pedidas: nada a simular (sem conflito possível); segue direto para a decisão da request."""
    res.avisos.append("nenhuma transação pedida: não houve análise de risco (o perfil é o ZBR do usuário de referência)")
    _decidir_e_criar(res, s, sap, grc_request, opcoes, requests_criadas, conflito=False, completa=True)
    return res


def _decidir_e_criar(res: Resultado, s: Solicitacao, sap: SapE1P, grc_request: GrcRequest, opcoes: Opcoes,
                     requests_criadas: int, *, conflito: bool, completa: bool) -> None:
    antes_do_submit = sap.usuario(s.igg)                # relido: alguém pode ter criado o usuário nesse meio tempo
    res.acao_request = decidir_request(
        s, antes_do_submit, conflito=conflito, analise_completa=completa,
        bloquear_com_conflito=opcoes.bloquear_com_conflito, executar=opcoes.executar,
        requests_criadas=requests_criadas, max_requests=opcoes.max_requests)
    if res.acao_request in (AcaoRequest.CRIAR, AcaoRequest.SIMULAR):
        _criar_ou_ensaiar(res, s, sap, grc_request)


def _criar_ou_ensaiar(res: Resultado, s: Solicitacao, sap: SapE1P, grc_request: GrcRequest) -> None:
    """CRIAR faz o Submit; SIMULAR (dry-run) preenche e confere o formulário do GRC sem clicar em Submit. Uma trava do
    formulário vira aviso; Submit sem confirmação NUNCA é repetido (a request pode existir)."""
    descricao = f"Criação de usuário {s.igg} (ZBR {res.zbr}) - Forms {s.id_resposta}"
    criar = res.acao_request is AcaoRequest.CRIAR

    def verificar() -> str | None:                      # com o formulário pronto, imediatamente antes do Submit
        u = sap.usuario(s.igg)
        if u.existe is False:
            return None
        return f"{s.igg} passou a existir no E1P" if u.existe else f"não deu para confirmar {s.igg} no E1P"

    try:
        res.request = grc_request.criar_usuario(s.igg, res.zbr, descricao, submeter=criar, verificar=verificar)
        if not criar:
            res.avisos.append("ensaio da request: formulário do GRC preenchido e conferido, Submit NÃO clicado (dry-run)")
    except SessaoParada:
        raise
    except (RequestBarrada, ErroValidacaoGrc) as e:
        res.acao_request = AcaoRequest.BARRADA_FORMULARIO
        res.avisos.append(f"request {'não criada' if criar else 'não passaria'}: {e}")
    except SubmitSemConfirmacao as e:
        res.acao_request = AcaoRequest.FALHOU_SUBMIT
        res.avisos.append(str(e))
    except Exception as e:  # noqa: BLE001 - falha de tela no meio do preenchimento: nada foi enviado
        log.exception("falha ao preencher a request de criação de %s", s.igg)
        res.acao_request = AcaoRequest.BARRADA_FORMULARIO
        res.avisos.append(f"request não {'criada' if criar else 'ensaiada'}: falha no formulário do GRC ({type(e).__name__}: {e})")
