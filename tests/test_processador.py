from datetime import datetime

import pytest

from gestao_usuarios.analise import Risco
from gestao_usuarios.decisao import Acao, AcaoRequest, UsuarioSap
from gestao_usuarios.erros import SessaoParada
from gestao_usuarios.processador import Opcoes, processar
from gestao_usuarios.seguranca import RegrasSeguranca
from gestao_usuarios.zbr import ListaZbr

from .conftest import FonteZbrFalsa, GrcRequestFalso, GrcRiscoFalso, SapFalso, solicitacao

AGORA = datetime(2026, 11, 17, 10, 0)
CRIACAO = dict(tipo="criacao", usuario_referencia="L7654321")
ROLES = {"FB01": ("Y-BRF-FI_A", "Y-BRF-FI_B"), "FB02": ("Y-BRF-FI_A",)}


def rodar(s, sap, risco=None, request=None, lista=None, fonte=None, **opcoes):
    risco = risco or GrcRiscoFalso()
    request = request or GrcRequestFalso()
    lista = lista if lista is not None else ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)})
    res = processar(s, regras=RegrasSeguranca(), sap=sap, grc_risco=risco, grc_request=request, lista_zbr=lista,
                    fonte_zbr=fonte, agora=AGORA, opcoes=Opcoes(**{"executar": True, **opcoes}))
    return res, risco, request


def test_modificacao_simula_no_igg_cada_single():
    sap = SapFalso({"L1234567": UsuarioSap(True)}, ROLES)
    alto = Risco("F1", "x", "High")
    res, risco, request = rodar(solicitacao(), sap, GrcRiscoFalso({"Y-BRF-FI_A": (alto,)}))
    assert res.acao is Acao.ANALISAR and res.alvo_simulacao == "L1234567"
    assert risco.simulados == [("L1234567", "Y-BRF-FI_A"), ("L1234567", "Y-BRF-FI_B"), ("L1234567", "Y-BRF-FI_A")]
    assert res.comparativo.recomendada("FB01").role == "Y-BRF-FI_B"
    assert res.comparativo.conflito
    assert res.acao_request is AcaoRequest.NAO_SE_APLICA and request.criadas == []


def test_recusada_nao_toca_no_sap():
    sap = SapFalso()
    res, _, _ = rodar(solicitacao(igg="X"), sap)
    assert res.recusada and sap.lidos == []


def test_criacao_de_usuario_que_ja_existe_avisa_e_nao_cria():
    sap = SapFalso({"L1234567": UsuarioSap(True), "L7654321": UsuarioSap(True)}, ROLES)
    res, risco, request = rodar(solicitacao(**CRIACAO), sap)
    assert res.acao is Acao.AVISAR_JA_EXISTE
    assert risco.simulados == [] and request.criadas == []


def test_criacao_sem_conflito_cria_request_com_zbr_da_referencia():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    res, risco, request = rodar(solicitacao(**CRIACAO), sap)
    assert res.alvo_simulacao == "L7654321" and {u for u, _ in risco.simulados} == {"L7654321"}
    assert res.acao_request is AcaoRequest.CRIAR and res.request == "700001"
    assert request.criadas[0][:2] == ("L1234567", "ZBRCOORD")
    assert sap.lidos.count("L1234567") == 3, "lido no início, relido antes de decidir e de novo com o formulário pronto"


def test_criacao_em_dry_run_nao_cria():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    res, _, request = rodar(solicitacao(**CRIACAO), sap, executar=False)
    assert res.acao_request is AcaoRequest.SIMULAR and request.criadas == []
    assert request.ensaios and request.ensaios[0][:2] == ("L1234567", "ZBRCOORD"), "dry-run ensaia o formulário sem submeter"
    assert any("Submit NÃO clicado" in a for a in res.avisos) and res.request is None


def test_verificacao_de_ultima_hora_roda_com_o_formulario_pronto():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    res, _, request = rodar(solicitacao(**CRIACAO), sap)
    assert request.verificacoes == [None] and res.request == "700001"


def test_trava_do_formulario_vira_aviso_sem_request():
    from gestao_usuarios.erros import UsuarioSemDadosNoGrc
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    request = GrcRequestFalso(UsuarioSemDadosNoGrc("o GRC não preencheu First Name"))
    res = processar(solicitacao(**CRIACAO), regras=RegrasSeguranca(), sap=sap, grc_risco=GrcRiscoFalso(), grc_request=request,
                    lista_zbr=ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)}), fonte_zbr=None, agora=AGORA,
                    opcoes=Opcoes(executar=True))
    assert res.acao_request is AcaoRequest.BARRADA_FORMULARIO and res.request is None
    assert any("não criada" in a and "First Name" in a for a in res.avisos)


def test_submit_sem_confirmacao_nunca_e_repetido():
    from gestao_usuarios.erros import SubmitSemConfirmacao
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    request = GrcRequestFalso(SubmitSemConfirmacao("Submit clicado, mas sem mensagem: CONFERIR no Request Status"))
    res = processar(solicitacao(**CRIACAO), regras=RegrasSeguranca(), sap=sap, grc_risco=GrcRiscoFalso(), grc_request=request,
                    lista_zbr=ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)}), fonte_zbr=None, agora=AGORA,
                    opcoes=Opcoes(executar=True))
    assert res.acao_request is AcaoRequest.FALHOU_SUBMIT and any("CONFERIR" in a for a in res.avisos)


def test_falha_de_tela_no_formulario_nao_cria_e_avisa():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    request = GrcRequestFalso(RuntimeError("tela inesperada"))
    res = processar(solicitacao(**CRIACAO), regras=RegrasSeguranca(), sap=sap, grc_risco=GrcRiscoFalso(), grc_request=request,
                    lista_zbr=ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)}), fonte_zbr=None, agora=AGORA,
                    opcoes=Opcoes(executar=True))
    assert res.acao_request is AcaoRequest.BARRADA_FORMULARIO and res.request is None and request.criadas == []


def test_criacao_com_conflito_nao_cria():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    res, _, request = rodar(solicitacao(**CRIACAO), sap, GrcRiscoFalso({"Y-BRF-FI_B": (Risco("L", "y", "Low"),)}))
    assert res.acao_request is AcaoRequest.BARRADA_CONFLITO and request.criadas == []


def test_usuario_criado_por_outro_no_meio_do_caminho_barra_request():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES, depois_da_primeira_leitura={"L1234567": UsuarioSap(True)})
    res, _, request = rodar(solicitacao(**CRIACAO), sap)
    assert res.acao_request is AcaoRequest.BARRADA_USUARIO_EXISTE and request.criadas == []


def test_simulacao_que_falha_barra_request_e_avisa():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    res, _, request = rodar(solicitacao(**CRIACAO), sap, GrcRiscoFalso(falhar={"Y-BRF-FI_B"}))
    assert res.acao_request is AcaoRequest.BARRADA_ANALISE_INCOMPLETA and request.criadas == []
    assert any("incompleta" in a for a in res.avisos)


def test_sessao_parada_sobe():
    class Expirou(GrcRiscoFalso):
        def simular(self, usuario, role):
            raise SessaoParada("GRC expirou")
    sap = SapFalso({"L1234567": UsuarioSap(True)}, ROLES)
    with pytest.raises(SessaoParada):
        rodar(solicitacao(), sap, Expirou())


def test_transacao_sem_single_vira_aviso():
    sap = SapFalso({"L1234567": UsuarioSap(True)}, {"FB01": ("Y-BRF-FI_A",)})
    res, _, _ = rodar(solicitacao(), sap)
    assert res.comparativo.sem_role == ["FB02"] and any("FB02" in a for a in res.avisos)


def test_zbr_fora_da_lista_vai_ao_o97():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    fonte = FonteZbrFalsa({"L7654321": ("ZBRFIN",)})
    res, _, request = rodar(solicitacao(**CRIACAO), sap, lista=ListaZbr(AGORA, {}), fonte=fonte)
    assert res.zbr == "ZBRFIN" and request.criadas[0][1] == "ZBRFIN"


def test_referencia_inexistente_avisa():
    sap = SapFalso({}, ROLES)
    res, risco, _ = rodar(solicitacao(**CRIACAO), sap)
    assert res.acao is Acao.AVISAR_REFERENCIA_NAO_EXISTE and risco.simulados == []


def test_disjuntor():
    sap = SapFalso({"L7654321": UsuarioSap(True)}, ROLES)
    risco, request = GrcRiscoFalso(), GrcRequestFalso()
    res = processar(solicitacao(**CRIACAO), regras=RegrasSeguranca(), sap=sap, grc_risco=risco, grc_request=request,
                    lista_zbr=ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)}), fonte_zbr=None, agora=AGORA,
                    opcoes=Opcoes(executar=True, max_requests=3), requests_criadas=3)
    assert res.acao_request is AcaoRequest.BARRADA_DISJUNTOR and request.criadas == []
