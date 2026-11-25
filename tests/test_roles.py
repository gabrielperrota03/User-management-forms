"""Índice transação -> single roles, vindo da extração da tabela de autorizações (roles.py)."""
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

import pytest

from gestao_usuarios.roles import ExtracaoInvalida, IndiceRoles, ler_xlsx
from gestao_usuarios.sap_e1p import SapE1PReal

CAB = {"A": "Role", "B": "ID", "C": "Authorization object", "D": "Auth", "F": "Field name", "G": "Authorization value",
       "H": "Authorization value", "J": "ID whether object is deleted"}
AGORA = datetime(2026, 11, 25, 14, 30)


def linha(role, valor, ate="", apagado="", objeto="S_TCODE"):
    return {"A": role, "B": "11", "C": objeto, "D": "T-1", "F": "TCD", "G": valor, "H": ate, "J": apagado}


def escrever_xlsx(caminho, linhas):
    """Planilha mínima com textos compartilhados (como o SAP exporta)."""
    textos: list[str] = []

    def idx(s):
        if s not in textos:
            textos.append(s)
        return textos.index(s)

    xml = ['<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for n, l in enumerate(linhas, start=1):
        xml.append(f'<row r="{n}">')
        for col, v in l.items():
            if v != "":
                xml.append(f'<c r="{col}{n}" t="s"><v>{idx(v)}</v></c>')
        xml.append("</row>")
    xml.append("</sheetData></worksheet>")
    ss = "".join(f"<si><t>{escape(t)}</t></si>" for t in textos)
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", "".join(xml))
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{ss}</sst>')


LINHAS = [CAB,
          linha("Y-BRF-FB01-POST_DOCUMENT", "FB01"), linha("Y-BRF-FB01-POST_DOCUMENT_BR02", "fb01"),
          linha("Y-BRA-DEPRECIATION_PROCESSING", "FB01"), linha("Y-BRA-DEPRECIATION_PROCESSING", "AS03"),
          linha("Y-BRX-APAGADA", "FB01", apagado="X"), linha("Y-BRX-OUTRO-OBJETO", "FB01", objeto="S_DEVELOP"),
          linha("Y-BRY-MENU_BI_REPORT", "YBIR*"), linha("Y-BRZ-FAIXA", "ZA01", ate="ZA09")]


def indice(tmp_path):
    arq = tmp_path / "extracao.xlsx"
    escrever_xlsx(arq, LINHAS)
    return IndiceRoles.da_extracao(ler_xlsx(arq), "extracao.xlsx", AGORA)


def test_leitor_de_xlsx(tmp_path):
    arq = tmp_path / "e.xlsx"
    escrever_xlsx(arq, LINHAS)
    linhas = ler_xlsx(arq)
    assert len(linhas) == len(LINHAS) and linhas[1]["A"] == "Y-BRF-FB01-POST_DOCUMENT" and linhas[1].get("H", "") == ""


def test_indice_ignora_apagadas_e_outros_objetos(tmp_path):
    i, ressalvas = indice(tmp_path)
    assert i.transacoes["FB01"] == ("Y-BRA-DEPRECIATION_PROCESSING", "Y-BRF-FB01-POST_DOCUMENT", "Y-BRF-FB01-POST_DOCUMENT_BR02")
    assert "Y-BRX-APAGADA" not in str(i.transacoes) and "Y-BRX-OUTRO-OBJETO" not in str(i.transacoes)
    assert len(ressalvas) == 1 and "Y-BRZ-FAIXA" in ressalvas[0] and "ZA01" not in i.transacoes


def test_consulta_prefere_roles_com_o_nome_da_transacao(tmp_path):
    i, _ = indice(tmp_path)
    assert i.singles_por_transacao("fb01") == ("Y-BRF-FB01-POST_DOCUMENT", "Y-BRF-FB01-POST_DOCUMENT_BR02")
    assert "só as 2 single roles com FB01" in i.avisos[0]
    assert i.singles_por_transacao("AS03") == ("Y-BRA-DEPRECIATION_PROCESSING",)         # nenhuma leva o nome: todas


def test_wildcard_vale_como_prefixo(tmp_path):
    i, _ = indice(tmp_path)
    assert i.singles_por_transacao("YBIR_QUALQUER") == ("Y-BRY-MENU_BI_REPORT",)
    assert i.singles_por_transacao("XYBIR") == ()


def test_transacao_fora_da_tabela_vira_aviso(tmp_path):
    i, _ = indice(tmp_path)
    assert i.singles_por_transacao("NAO_EXISTE") == ()
    assert "NAO_EXISTE: transação não está na tabela de roles (extração de 25/11/2026)" in i.avisos


def test_json_ida_e_volta(tmp_path):
    i, _ = indice(tmp_path)
    arq = tmp_path / "idx.json"
    i.salvar(arq)
    de_volta = IndiceRoles.carregar(arq)
    assert de_volta.transacoes == i.transacoes and de_volta.gerado_em == AGORA and de_volta.origem == "extracao.xlsx"
    assert IndiceRoles.carregar(tmp_path / "nao_existe.json") is None


@pytest.mark.parametrize("mudar", [{"A": "Papel"}, {"C": "Objeto"}, {"G": "Valor"}, {"J": "Deleted"}])
def test_formato_diferente_nao_gera_nada(mudar):
    with pytest.raises(ExtracaoInvalida, match="formato da extração mudou"):
        IndiceRoles.da_extracao([{**CAB, **mudar}, linha("Y-BRF-FB01-POST_DOCUMENT", "FB01")], "x", AGORA)


def test_planilha_vazia_ou_sem_s_tcode():
    with pytest.raises(ExtracaoInvalida):
        IndiceRoles.da_extracao([], "x", AGORA)
    with pytest.raises(ExtracaoInvalida, match="nenhuma linha"):
        IndiceRoles.da_extracao([CAB, linha("Y-BRX", "FB01", objeto="S_DEVELOP")], "x", AGORA)


def test_sap_e1p_usa_o_indice_sem_tocar_na_sessao(tmp_path):
    i, _ = indice(tmp_path)

    class SessaoQueNaoPodeSerTocada:
        def __getattr__(self, nome):
            raise AssertionError("o índice não pode usar a sessão do SAP")

    sap = SapE1PReal(SessaoQueNaoPodeSerTocada(), None, tmp_path, roles=i)
    assert sap.singles_por_transacao("FB01") == ("Y-BRF-FB01-POST_DOCUMENT", "Y-BRF-FB01-POST_DOCUMENT_BR02")
    assert sap.avisos and sap.prints == []
    sap.limpar(tmp_path)
    assert sap.avisos == []
