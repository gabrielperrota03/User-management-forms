"""O Forms ramifica por seção (Criação / Modificação): JSON com uma chave por pergunta, e criação sem campo de transações."""
from datetime import datetime

import pytest

from gestao_usuarios import relatorio
from gestao_usuarios.decisao import AcaoRequest, UsuarioSap
from gestao_usuarios.processador import Opcoes, processar
from gestao_usuarios.resposta import Tipo, de_dict
from gestao_usuarios.seguranca import RegrasSeguranca, avaliar_solicitacao
from gestao_usuarios.zbr import ListaZbr

from .conftest import GrcRequestFalso, GrcRiscoFalso, SapFalso

AGORA = datetime(2026, 11, 24, 9, 0)
BASE = {"id_resposta": "7", "enviado_em": "2026-11-24T12:00:00Z", "solicitante_nome": "Fulano de Tal",
        "solicitante_email": "fulano.tal@totalenergies.com"}
CRIACAO = {**BASE, "tipo": "Criação de usuário", "criacao_igg": "l1234567", "criacao_referencia": "L7654321",
           "criacao_justificativa": "Analista de custos, diretoria financeira",
           "modificacao_igg": "", "modificacao_transacoes": "", "modificacao_justificativa": ""}
MODIFICACAO = {**BASE, "tipo": "Modificação de acesso", "modificacao_igg": "L1234567", "modificacao_transacoes": "fb01\nFB02",
               "modificacao_justificativa": "Lançamentos", "criacao_igg": "", "criacao_referencia": "", "criacao_justificativa": ""}


def test_criacao_le_as_chaves_da_secao_de_criacao():
    s = de_dict(CRIACAO, "a.json")
    assert s.tipo is Tipo.CRIACAO and s.igg == "L1234567" and s.usuario_referencia == "L7654321"
    assert s.transacoes == () and s.justificativa.startswith("Analista")


def test_modificacao_le_as_chaves_da_secao_de_modificacao():
    s = de_dict(MODIFICACAO, "a.json")
    assert s.tipo is Tipo.MODIFICACAO and s.igg == "L1234567" and s.transacoes == ("FB01", "FB02")
    assert s.usuario_referencia is None and s.justificativa == "Lançamentos"


def test_chaves_antigas_continuam_valendo():
    s = de_dict({**BASE, "tipo": "Modificação de acesso", "igg": "L1234567", "transacoes": "FB01", "justificativa": "x"}, "a.json")
    assert (s.igg, s.transacoes, s.justificativa) == ("L1234567", ("FB01",), "x")


def test_resposta_da_outra_secao_nao_vaza():
    """Uma modificação não pode herdar o IGG ou a justificativa da seção de criação, e vice-versa."""
    misturada = {**MODIFICACAO, "criacao_igg": "L9999999", "criacao_justificativa": "outra"}
    s = de_dict(misturada, "a.json")
    assert s.igg == "L1234567" and s.justificativa == "Lançamentos"


def test_transacoes_so_sao_obrigatorias_na_modificacao():
    r = RegrasSeguranca()
    assert avaliar_solicitacao(de_dict(CRIACAO, "a.json"), r) == []
    sem = avaliar_solicitacao(de_dict({**MODIFICACAO, "modificacao_transacoes": ""}, "a.json"), r)
    assert any("nenhuma transação" in m for m in sem)


def test_criacao_sem_referencia_e_barrada():
    m = avaliar_solicitacao(de_dict({**CRIACAO, "criacao_referencia": ""}, "a.json"), RegrasSeguranca())
    assert any("sem usuário de referência" in x for x in m)


def _rodar(executar):
    sap = SapFalso({"L7654321": UsuarioSap(True)}, {})
    risco, request = GrcRiscoFalso(), GrcRequestFalso()
    res = processar(de_dict(CRIACAO, "a.json"), regras=RegrasSeguranca(), sap=sap, grc_risco=risco, grc_request=request,
                    lista_zbr=ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)}), fonte_zbr=None, agora=AGORA,
                    opcoes=Opcoes(executar=executar))
    return res, risco, request


def test_criacao_sem_transacoes_nao_simula_e_cria_a_request():
    res, risco, request = _rodar(True)
    assert res.sem_analise and res.comparativo is None and risco.simulados == []
    assert res.acao_request is AcaoRequest.CRIAR and request.criadas == [
        ("L1234567", "ZBRCOORD", "Criação de usuário L1234567 (ZBR ZBRCOORD) - Forms 7")]
    assert res.avisos == []                              # a criação não tem análise por desenho: o e-mail próprio explica


def test_criacao_sem_transacoes_em_dry_run_so_ensaia():
    res, risco, request = _rodar(False)
    assert res.acao_request is AcaoRequest.SIMULAR and request.criadas == [] and len(request.ensaios) == 1


def test_relatorio_da_criacao_sem_transacoes():
    res, _, _ = _rodar(False)
    assert relatorio.situacao(res) == "PARA CRIAR"
    assert relatorio.assunto(res) == "[gestao-usuarios] Criação L1234567 - PARA CRIAR (ZBR ZBRCOORD)"
    html = relatorio.montar_html(res, [], AGORA)
    assert "PARA CRIAR" in html and "Transações" not in html and "Análise de risco" not in html


@pytest.mark.parametrize("acao", [AcaoRequest.BARRADA_FORMULARIO, AcaoRequest.FALHOU_SUBMIT])
def test_falha_da_request_na_criacao_sem_transacoes_e_aviso(acao):
    res, _, _ = _rodar(False)
    res.acao_request = acao
    assert relatorio.situacao(res) == "AVISO"


# Resposta crua como o fluxo do Power Automate grava (chaves = IDs das perguntas do Forms; valores de teste)
CRUA_BASE = {"responder": "Fulano.Tal@totalenergies.com", "submitDate": "11/23/2026 4:20:06 PM", "id_resposta": "9"}
CRUA_CRIACAO = {**CRUA_BASE, "re72ac6907e2d4cab8bdfd5be73b385db": "Criação de usuário",
                "r1b4568cc37574ca3977384e4e5a19dec": "l1234567", "r886c8288e16e4395b18dd31413a8b751": "l7654321",
                "rf821d5f8f8604eb78ff9f1796ad0de52": "", "r4e7aee5435694475a7b383ad319db54b": "Analista de custos",
                "r4a2c00f93e374f2aa59595244af7651c": "", "rd5822024821e4e7f8b25a2ef94ea40e0": ""}
CRUA_MODIFICACAO = {**CRUA_BASE, "re72ac6907e2d4cab8bdfd5be73b385db": "Modificação de acesso",
                    "r1b4568cc37574ca3977384e4e5a19dec": "", "r886c8288e16e4395b18dd31413a8b751": "",
                    "rf821d5f8f8604eb78ff9f1796ad0de52": "fb01, FB02",
                    "r4e7aee5435694475a7b383ad319db54b": "",
                    "r4a2c00f93e374f2aa59595244af7651c": "Lançamentos", "rd5822024821e4e7f8b25a2ef94ea40e0": "L1234567"}


def test_resposta_crua_do_forms_na_criacao():
    s = de_dict(CRUA_CRIACAO, "a.json")
    assert s.tipo is Tipo.CRIACAO and s.igg == "L1234567" and s.usuario_referencia == "L7654321"
    assert s.transacoes == () and s.justificativa == "Analista de custos" and s.id_resposta == "9"
    assert s.solicitante_email == "fulano.tal@totalenergies.com" and s.enviado_em == "11/23/2026 4:20:06 PM"


def test_resposta_crua_do_forms_na_modificacao():
    s = de_dict(CRUA_MODIFICACAO, "a.json")
    assert s.tipo is Tipo.MODIFICACAO and s.igg == "L1234567" and s.transacoes == ("FB01", "FB02")
    assert s.usuario_referencia is None and s.justificativa == "Lançamentos"
    assert avaliar_solicitacao(s, RegrasSeguranca()) == []


def test_id_da_resposta_numerico_do_forms():
    """O Forms entrega o Response Id como número no JSON (visto no teste ponta a ponta de 23/11/2026)."""
    s = de_dict({**CRUA_MODIFICACAO, "id_resposta": 3}, "a.json")
    assert s.id_resposta == "3"


def test_manifesto_tolera_bom(tmp_path):
    from gestao_usuarios.manifesto import Manifesto
    arq = tmp_path / "estado.json"
    arq.write_bytes(b"\xef\xbb\xbf{}")
    assert Manifesto(arq).entradas == {}


def test_recorte_do_print_tira_o_fundo_vazio():
    from PIL import Image, ImageDraw
    from gestao_usuarios.capturas import recortar_conteudo
    im = Image.new("RGB", (2000, 1000), (242, 242, 242))
    ImageDraw.Draw(im).rectangle((10, 20, 509, 219), fill=(0, 0, 0))
    r = recortar_conteudo(im, margem=10)
    assert r.size == (520, 220)
    assert recortar_conteudo(Image.new("RGB", (50, 50), (242, 242, 242))).size == (50, 50)      # tela vazia: não corta


def test_quadro_do_relatorio_mostra_so_criticos_e_o_detalhe_completo():
    from gestao_usuarios.analise import Risco, ResultadoRole, comparar
    from gestao_usuarios.processador import Resultado
    s = de_dict(MODIFICACAO, "a.json")
    riscos = (Risco("CFI01_EP", "Finance Critical Transactions", "Critical"),
              Risco("XPTO", "Outro risco", "Medium"))
    from gestao_usuarios.decisao import Acao
    res = Resultado(s, acao=Acao.ANALISAR)
    res.comparativo = comparar(("FB01",), [ResultadoRole("FB01", "Y-BRF-FB01-POST_DOCUMENT", riscos)])
    html = relatorio.montar_html(res, [], AGORA)
    assert "<th>Críticos</th>" in html and "<th>High</th>" not in html and "<th>Medium</th>" not in html
    assert "CFI01_EP" in html and "XPTO" in html            # o detalhe continua listando todos os riscos


# ------------------------------------------------------------------ request desligada e e-mail próprio da criação
def _rodar_com(usuarios, zbrs, request_grc=False, referencia="L7654321"):
    sap = SapFalso(usuarios, {})
    risco, request = GrcRiscoFalso(), GrcRequestFalso()
    res = processar(de_dict({**CRIACAO, "criacao_referencia": referencia}, "a.json"), regras=RegrasSeguranca(), sap=sap,
                    grc_risco=risco, grc_request=request, lista_zbr=ListaZbr(AGORA, zbrs), fonte_zbr=None, agora=AGORA,
                    opcoes=Opcoes(executar=True, request_grc=request_grc))
    return res, sap, risco, request


def test_request_desligada_nao_toca_no_grc_nem_ensaia():
    res, sap, risco, request = _rodar_com({"L7654321": UsuarioSap(True)}, {"L7654321": ("ZBRCOORD",)})
    assert res.acao_request is AcaoRequest.DESLIGADA
    assert request.criadas == [] and request.ensaios == [] and risco.simulados == []
    assert sap.lidos == ["L1234567", "L7654321"], "sem a releitura de antes do Submit: não há Submit"
    assert relatorio.situacao(res) == "PARA CRIAR"


def test_email_da_criacao_tem_estrutura_propria():
    res, *_ = _rodar_com({"L7654321": UsuarioSap(True)}, {"L7654321": ("ZBRCOORD",)})
    html = relatorio.montar_html(res, [], AGORA)
    for esperado in ("Pedido de criação de usuário SAP (E1P)", "Novo usuário (IGG)", "Perfil a atribuir (ZBR)", "ZBRCOORD",
                     "Conferências no E1P", "O novo usuário ainda não existe no E1P", "O usuário de referência existe no E1P",
                     "ZBR do usuário de referência", "Tudo conferido", "não foi aberta"):
        assert esperado in html, esperado
    for proibido in ("Solicitação de acesso SAP", "Transações", "Análise de risco", "Tipo</th>"):
        assert proibido not in html, proibido


def test_email_da_modificacao_continua_com_a_sua_estrutura():
    from gestao_usuarios.processador import Resultado
    res = Resultado(de_dict(MODIFICACAO, "a.json"), acao=__import__("gestao_usuarios.decisao", fromlist=["Acao"]).Acao.ANALISAR)
    html = relatorio.montar_html(res, [], AGORA)
    assert "Solicitação de acesso SAP (E1P)" in html and "Modificação de acesso" in html and "Transações" in html
    assert "Conferências no E1P" not in html and "Perfil a atribuir" not in html


def test_email_da_criacao_quando_o_usuario_ja_existe():
    res, _, _, request = _rodar_com({"L1234567": UsuarioSap(True), "L7654321": UsuarioSap(True)}, {"L7654321": ("ZBRCOORD",)})
    html = relatorio.montar_html(res, [], AGORA)
    assert relatorio.situacao(res) == "AVISO" and request.criadas == []
    assert "JÁ EXISTE" in html and "não verificado" in html and "já existe no E1P" in html
    assert relatorio.assunto(res) == "[gestao-usuarios] Criação L1234567 - AVISO (ref. L7654321)"


def test_email_da_criacao_com_referencia_inexistente_ou_sem_zbr_ou_varios():
    res, *_ = _rodar_com({}, {})
    html = relatorio.montar_html(res, [], AGORA)
    assert relatorio.situacao(res) == "AVISO" and "NÃO EXISTE" in html and "não verificado" in html

    res, *_ = _rodar_com({"L7654321": UsuarioSap(True)}, {})
    assert relatorio.situacao(res) == "AVISO" and "NENHUM" in relatorio.montar_html(res, [], AGORA)

    res, *_ = _rodar_com({"L7654321": UsuarioSap(True)}, {"L7654321": ("ZBRA", "ZBRB")})
    html = relatorio.montar_html(res, [], AGORA)
    assert relatorio.situacao(res) == "AVISO" and "VÁRIOS" in html and "ZBRA, ZBRB" in html
    assert relatorio.assunto(res) == "[gestao-usuarios] Criação L1234567 - AVISO (ZBR ZBRA, ZBRB)"


def test_email_da_criacao_com_leitura_incerta():
    res, *_ = _rodar_com({"L1234567": UsuarioSap(None)}, {})
    html = relatorio.montar_html(res, [], AGORA)
    assert relatorio.situacao(res) == "AVISO" and "NÃO CONFIRMADO" in html


def test_request_criada_aparece_na_situacao_e_no_texto():
    res, *_ = _rodar_com({"L7654321": UsuarioSap(True)}, {"L7654321": ("ZBRCOORD",)}, request_grc=True)
    assert res.acao_request is AcaoRequest.CRIAR
    assert relatorio.situacao(res) == "REQUEST CRIADA" and "Request de criação criada" in relatorio.montar_html(res, [], AGORA)


@pytest.mark.parametrize("texto,tipo", [
    ("Criação de usuário / User creation", Tipo.CRIACAO), ("Modificação de acesso / Access modification", Tipo.MODIFICACAO),
    ("Criação de usuário", Tipo.CRIACAO), ("Modificação de acesso", Tipo.MODIFICACAO),
    ("User creation / Criação de usuário", Tipo.CRIACAO), ("Access modification", Tipo.MODIFICACAO),
    ("  CRIAÇÃO DE USUÁRIO / USER CREATION ", Tipo.CRIACAO)])
def test_tipo_no_forms_bilingue(texto, tipo):
    from gestao_usuarios.resposta import ler_tipo
    assert ler_tipo(texto) is tipo


def test_resposta_crua_do_forms_bilingue():
    s = de_dict({**CRUA_CRIACAO, "re72ac6907e2d4cab8bdfd5be73b385db": "Criação de usuário / User creation"}, "a.json")
    assert s.tipo is Tipo.CRIACAO and s.igg == "L1234567"
    m = de_dict({**CRUA_MODIFICACAO, "re72ac6907e2d4cab8bdfd5be73b385db": "Modificação de acesso / Access modification"}, "a.json")
    assert m.tipo is Tipo.MODIFICACAO and m.transacoes == ("FB01", "FB02")


def test_tipo_desconhecido_continua_recusado():
    from gestao_usuarios.resposta import RespostaInvalida, ler_tipo
    for ruim in ("", "outro", None, "Deletion / Exclusão"):
        with pytest.raises(RespostaInvalida):
            ler_tipo(ruim)
