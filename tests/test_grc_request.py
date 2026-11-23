"""Request de criação no GRC: conferências do formulário e da grade (sem GRC real). Valores conforme a tela de 23/11/2026."""
import pytest

from gestao_usuarios.config import carregar
from gestao_usuarios.erros import RequestBarrada
from gestao_usuarios.grc_request import (ConfigGrcRequest, GrcRequestPlaywright, RE_ZBR, conferir_formulario, conferir_grade,
                                         dados_do_usuario_completos, erros_de_validacao, linha_do_resultado,
                                         numero_da_request, validar_entrada)

C = ConfigGrcRequest.de_config(carregar(usar_local=False))
FORM = {"Request Type": "New or Change Account", "Request For": "Other", "User": "L1234567",
        "Functional Area": "EP- BRAZIL", "User Group Name": "BR-TEP", "Description": "Criação de usuário L1234567"}
LINHA = {"Assignment": "ZBRCOORD", "System": "", "Type": "Business Role", "Valid From": "23.11.2026", "Valid To": "31.12.9999",
         "Assignment Approver": "J0025020(3)", "Description": "Coordinator SAP", "Provisioning Environment": "All",
         "Provisioning Action": "Assign", "Provisioning Status": "Not Processed"}


def test_config():
    assert (C.functional_area, C.user_group, C.tipo, C.tipo_role) == ("EP- BRAZIL", "BR-TEP", "New or Change Account",
                                                                      "Business Role")
    assert C.url.startswith("https://sapo97")


def test_numero_da_request_e_erros():
    assert numero_da_request("Request submitted successfully; the request number is 675385") == "675385"
    assert numero_da_request("Request number is\n 12") == "12" and numero_da_request("erro") is None
    assert erros_de_validacao("x\nEnter the value for First Name\nEnter the value for Email") == [
        "Enter the value for First Name", "Enter the value for Email"]


@pytest.mark.parametrize("zbr,ok", [("ZBRCOORD", True), ("ZBR_COORD", True), ("ZBRBUY&STK", True), ("ZBRRELEASER2", True),
                                    ("ZBR", False), ("COORD", False), ("ZBR COORD", False), ("zbrcoord", False), ("", False),
                                    ("ZBR*", False)])
def test_formato_do_zbr(zbr, ok):
    assert bool(RE_ZBR.match(zbr)) is ok


@pytest.mark.parametrize("igg,zbr,desc", [("L12", "ZBRCOORD", "x"), ("L1234567", "COORD", "x"), ("L1234567", "ZBRCOORD", "  ")])
def test_entrada_invalida_nao_abre_formulario(igg, zbr, desc):
    with pytest.raises(RequestBarrada):
        validar_entrada(igg, zbr, desc)
    with pytest.raises(RequestBarrada):
        GrcRequestPlaywright(None, C).criar_usuario(igg, zbr, desc)         # contexto None: nem chegou a abrir
    validar_entrada("L1234567", "ZBRCOORD", "ok")


def test_formulario_confere():
    assert conferir_formulario(FORM, C, "L1234567", "Criação de usuário L1234567") == []
    assert conferir_formulario({**FORM, "User": "l1234567"}, C, "L1234567", "Criação de usuário L1234567") == []


@pytest.mark.parametrize("campo,valor", [("Request Type", "Lock Account"), ("Request For", "Self"), ("User", "L7654321"),
                                         ("Functional Area", "Select"), ("User Group Name", ""), ("Description", "outra")])
def test_formulario_divergente(campo, valor):
    erros = conferir_formulario({**FORM, campo: valor}, C, "L1234567", "Criação de usuário L1234567")
    assert len(erros) == 1 and campo in erros[0]


def test_grade_confere():
    assert conferir_grade([LINHA], C, "ZBRCOORD") == []


@pytest.mark.parametrize("linhas,trecho", [
    ([], "0 linhas"),
    ([LINHA, LINHA], "2 linhas"),
    ([{**LINHA, "Assignment": "ZBRFI"}], "Assignment"),
    ([{**LINHA, "Type": "Single Role"}], "Type"),
    ([{**LINHA, "Provisioning Action": "Remove"}], "Provisioning Action"),
    ([{**LINHA, "Valid To": "31.12.2026"}], "Valid To"),
])
def test_grade_divergente(linhas, trecho):
    erros = conferir_grade(linhas, C, "ZBRCOORD")
    assert erros and any(trecho in e for e in erros)


def test_dados_do_usuario():
    assert dados_do_usuario_completos({"First Name": "Gabriel", "Last Name": "PERROTA", "Email": "g@x.com"}) == []
    assert dados_do_usuario_completos({"First Name": "", "Last Name": " ", "Email": "g@x.com"}) == ["First Name", "Last Name"]
    assert dados_do_usuario_completos({}) == ["First Name", "Last Name", "Email"]


def test_linha_do_resultado_exige_exatamente_uma():
    achada = {"Role Name": "ZBRCOORD", "Role Type": "Business Role", "Description": "Coordinator SAP"}
    outra = {"Role Name": "ZBRCOORD2", "Role Type": "Business Role"}
    assert linha_do_resultado([outra, achada], "ZBRCOORD", "Business Role") == 2
    for linhas in ([], [outra], [achada, achada], [{**achada, "Role Type": "Composite Role"}]):
        with pytest.raises(RequestBarrada, match="exatamente uma vez"):
            linha_do_resultado(linhas, "ZBRCOORD", "Business Role")


def test_submit_e_impossivel_em_modo_de_teste_de_tela():
    g = GrcRequestPlaywright(None, C, exigir_dados_usuario=False)
    with pytest.raises(ValueError, match="Submit é impossível"):
        g.criar_usuario("L1234567", "ZBRCOORD", "x", submeter=True)
