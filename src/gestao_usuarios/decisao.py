"""Regras de decisão (docs/ARQUITETURA.md, seções 4 e 7). Funções puras: não tocam em SAP, GRC nem disco."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .resposta import Solicitacao, Tipo


@dataclass(frozen=True)
class UsuarioSap:
    """Leitura da SU01D no E1P. `existe=None` = leitura incerta (trata como desconhecido: não age)."""
    existe: bool | None
    bloqueado: bool | None = None


class Acao(StrEnum):
    ANALISAR = "analisar"
    AVISAR_LEITURA_INCERTA = "avisar_leitura_incerta"
    AVISAR_JA_EXISTE = "avisar_ja_existe"                  # criação de quem já existe no SAP: guarda de segurança
    AVISAR_REFERENCIA_NAO_EXISTE = "avisar_referencia_nao_existe"
    AVISAR_SEM_ZBR = "avisar_sem_zbr"
    AVISAR_VARIOS_ZBR = "avisar_varios_zbr"


def decidir_entrada(s: Solicitacao, usuario: UsuarioSap | None, referencia: UsuarioSap | None = None,
                    zbrs: tuple[str, ...] | None = None) -> tuple[Acao, str]:
    """Depois das guardas de segurança: a solicitação segue para a análise ou vira aviso? A primeira regra que valer encerra.
    Modificação não confere o usuário no E1P (analista, 25/11/2026: a análise de risco basta): `usuario` vem None."""
    if s.tipo is Tipo.MODIFICACAO:
        return Acao.ANALISAR, "modificação: só a análise de risco (o usuário não é conferido no E1P)"
    if usuario is None or usuario.existe is None:
        return Acao.AVISAR_LEITURA_INCERTA, f"não foi possível confirmar se {s.igg} existe no E1P"
    if s.tipo is Tipo.CRIACAO:
        if usuario.existe:
            return Acao.AVISAR_JA_EXISTE, f"{s.igg} já existe no E1P: criação recusada, verificar se o pedido é modificação"
        if referencia is None or referencia.existe is None:
            return Acao.AVISAR_LEITURA_INCERTA, f"não foi possível confirmar o usuário de referência {s.usuario_referencia}"
        if not referencia.existe:
            return Acao.AVISAR_REFERENCIA_NAO_EXISTE, f"usuário de referência {s.usuario_referencia} não existe no E1P"
        if not zbrs:
            return Acao.AVISAR_SEM_ZBR, f"nenhum ZBR encontrado para o usuário de referência {s.usuario_referencia}"
        if len(zbrs) > 1:
            return Acao.AVISAR_VARIOS_ZBR, (f"usuário de referência {s.usuario_referencia} tem mais de um ZBR "
                                            f"({', '.join(zbrs)}): escolher à mão")
        return Acao.ANALISAR, f"criação com ZBR {zbrs[0]} (de {s.usuario_referencia})"


def alvo_da_simulacao(s: Solicitacao) -> str:
    """Modificação: o próprio IGG. Criação: o IGG ainda não existe no SAP, então o usuário de referência (mesmo ZBR)."""
    return s.usuario_referencia if s.tipo is Tipo.CRIACAO and s.usuario_referencia else s.igg


class AcaoRequest(StrEnum):
    NAO_SE_APLICA = "nao_se_aplica"                        # modificação: não há request
    DESLIGADA = "desligada"                                # criação com a request no GRC desligada (request.ligada: false): só o e-mail
    CRIAR = "criar"
    SIMULAR = "simular"                                    # dry-run: o relatório mostra "criaria"
    BARRADA_USUARIO_EXISTE = "barrada_usuario_existe"
    BARRADA_LEITURA_INCERTA = "barrada_leitura_incerta"
    BARRADA_CONFLITO = "barrada_conflito"
    BARRADA_ANALISE_INCOMPLETA = "barrada_analise_incompleta"
    BARRADA_DISJUNTOR = "barrada_disjuntor"
    BARRADA_FORMULARIO = "barrada_formulario"              # trava do próprio formulário do GRC (dados do usuário, ZBR, conferência)
    FALHOU_SUBMIT = "falhou_submit"                        # GRC recusou o Submit ou ele ficou sem confirmação: um humano confere


def decidir_request(s: Solicitacao, usuario_antes_do_submit: UsuarioSap, *, conflito: bool, analise_completa: bool,
                    bloquear_com_conflito: bool, executar: bool, requests_criadas: int, max_requests: int) -> AcaoRequest:
    """Só criação, só usuário novo (relido no SAP logo antes do Submit), nunca às cegas."""
    if s.tipo is not Tipo.CRIACAO:
        return AcaoRequest.NAO_SE_APLICA
    if usuario_antes_do_submit.existe is None:
        return AcaoRequest.BARRADA_LEITURA_INCERTA
    if usuario_antes_do_submit.existe:
        return AcaoRequest.BARRADA_USUARIO_EXISTE
    if not analise_completa:
        return AcaoRequest.BARRADA_ANALISE_INCOMPLETA
    if conflito and bloquear_com_conflito:
        return AcaoRequest.BARRADA_CONFLITO
    if not executar:
        return AcaoRequest.SIMULAR
    if requests_criadas >= max_requests:
        return AcaoRequest.BARRADA_DISJUNTOR
    return AcaoRequest.CRIAR
