import itertools

import pytest

from gestao_usuarios.analise import Risco, ResultadoRole, comparar, normalizar_nivel
from gestao_usuarios.decisao import (Acao, AcaoRequest, UsuarioSap, alvo_da_simulacao, decidir_entrada,
                                     decidir_request)

from .conftest import solicitacao

EXISTE, NAO_EXISTE, INCERTO = UsuarioSap(True), UsuarioSap(False), UsuarioSap(None)
CRIACAO = dict(tipo="criacao", usuario_referencia="L7654321")


def test_modificacao():
    s = solicitacao()
    assert decidir_entrada(s, EXISTE)[0] is Acao.ANALISAR
    assert decidir_entrada(s, NAO_EXISTE)[0] is Acao.AVISAR_NAO_EXISTE
    assert decidir_entrada(s, INCERTO)[0] is Acao.AVISAR_LEITURA_INCERTA
    assert alvo_da_simulacao(s) == "L1234567"


def test_criacao():
    s = solicitacao(**CRIACAO)
    assert decidir_entrada(s, EXISTE, EXISTE, ("ZBRCOORD",))[0] is Acao.AVISAR_JA_EXISTE
    assert decidir_entrada(s, NAO_EXISTE, NAO_EXISTE, None)[0] is Acao.AVISAR_REFERENCIA_NAO_EXISTE
    assert decidir_entrada(s, NAO_EXISTE, INCERTO, None)[0] is Acao.AVISAR_LEITURA_INCERTA
    assert decidir_entrada(s, NAO_EXISTE, None, None)[0] is Acao.AVISAR_LEITURA_INCERTA
    assert decidir_entrada(s, NAO_EXISTE, EXISTE, ())[0] is Acao.AVISAR_SEM_ZBR
    assert decidir_entrada(s, NAO_EXISTE, EXISTE, ("ZBRA", "ZBRB"))[0] is Acao.AVISAR_VARIOS_ZBR
    assert decidir_entrada(s, NAO_EXISTE, EXISTE, ("ZBRCOORD",))[0] is Acao.ANALISAR
    assert alvo_da_simulacao(s) == "L7654321"


def _req(s, usuario, **kw):
    base = dict(conflito=False, analise_completa=True, bloquear_com_conflito=True, executar=True,
                requests_criadas=0, max_requests=3)
    return decidir_request(s, usuario, **{**base, **kw})


def test_request_so_na_criacao_de_usuario_novo():
    criacao = solicitacao(**CRIACAO)
    assert _req(solicitacao(), NAO_EXISTE) is AcaoRequest.NAO_SE_APLICA
    assert _req(criacao, NAO_EXISTE) is AcaoRequest.CRIAR
    assert _req(criacao, EXISTE) is AcaoRequest.BARRADA_USUARIO_EXISTE
    assert _req(criacao, INCERTO) is AcaoRequest.BARRADA_LEITURA_INCERTA
    assert _req(criacao, NAO_EXISTE, analise_completa=False) is AcaoRequest.BARRADA_ANALISE_INCOMPLETA
    assert _req(criacao, NAO_EXISTE, conflito=True) is AcaoRequest.BARRADA_CONFLITO
    assert _req(criacao, NAO_EXISTE, conflito=True, bloquear_com_conflito=False) is AcaoRequest.CRIAR
    assert _req(criacao, NAO_EXISTE, executar=False) is AcaoRequest.SIMULAR
    assert _req(criacao, NAO_EXISTE, requests_criadas=3) is AcaoRequest.BARRADA_DISJUNTOR


def test_grade_request_nunca_cria_para_quem_existe_ou_e_incerto():
    """Regra de ouro: em nenhuma combinação a request de criação sai para usuário que existe ou leitura incerta."""
    for tipo, usuario, conflito, completa, bloquear, executar, criadas in itertools.product(
            ("criacao", "modificacao"), (EXISTE, NAO_EXISTE, INCERTO), (False, True), (False, True), (False, True),
            (False, True), (0, 5)):
        s = solicitacao(tipo=tipo, usuario_referencia="L7654321")
        acao = _req(s, usuario, conflito=conflito, analise_completa=completa, bloquear_com_conflito=bloquear,
                    executar=executar, requests_criadas=criadas)
        if acao is AcaoRequest.CRIAR:
            assert tipo == "criacao" and usuario is NAO_EXISTE and completa and executar and criadas < 3
            assert not (conflito and bloquear)


def test_nivel_desconhecido_conta_como_critical():
    assert normalizar_nivel("high") == "High"
    assert normalizar_nivel("") == "Critical" and normalizar_nivel("Muito alto") == "Critical"


def test_comparar_ordena_e_marca_conflito(risco_alto):
    crit = Risco("C1", "x", "Critical")
    low = Risco("L1", "y", "Low")
    comp = comparar(("FB01", "FB02", "ME21N"), [
        ResultadoRole("FB01", "Y-BR-A", (crit,)),
        ResultadoRole("FB01", "Y-BR-B", (risco_alto, risco_alto)),
        ResultadoRole("FB01", "Y-BR-C", erro="falhou"),
        ResultadoRole("FB02", "Y-BR-D", ()),
    ])
    assert [r.role for r in comp.por_transacao["FB01"]] == ["Y-BR-B", "Y-BR-A", "Y-BR-C"]
    assert comp.recomendada("FB01").role == "Y-BR-B"
    assert comp.recomendada("ME21N") is None and comp.sem_role == ["ME21N"]
    assert comp.conflito and not comp.completo
    assert comp.por_transacao["FB01"][1].nivel_mais_grave == "Critical"
    assert comp.por_transacao["FB01"][1].contagem()["Critical"] == 1

    so_low = comparar(("FB02",), [ResultadoRole("FB02", "Y-BR-D", (low,))])
    assert so_low.conflito, "qualquer nível de risco é conflito"
    sem_risco = comparar(("FB02",), [ResultadoRole("FB02", "Y-BR-D", ())])
    assert not sem_risco.conflito and sem_risco.completo


@pytest.mark.parametrize("erro", ["falhou"])
def test_simulacao_com_erro_nao_e_recomendada(erro):
    comp = comparar(("FB01",), [ResultadoRole("FB01", "Y-BR-A", erro=erro)])
    assert comp.recomendada("FB01") is None and not comp.conflito and not comp.completo
