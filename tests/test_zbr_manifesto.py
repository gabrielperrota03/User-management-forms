from datetime import datetime, timedelta

from gestao_usuarios.manifesto import Entrada, Fase, Manifesto
from gestao_usuarios.zbr import ListaZbr, filtrar_zbr, resolver_zbr

from .conftest import FonteZbrFalsa

AGORA = datetime(2026, 11, 17, 10, 0)


def test_lista_ida_e_volta(tmp_path):
    caminho = tmp_path / "zbr.json"
    ListaZbr(AGORA, {"l7654321": ("ZBRCOORD",)}).salvar(caminho)
    lista = ListaZbr.carregar(caminho)
    assert lista.usuarios == {"L7654321": ("ZBRCOORD",)} and lista.gerado_em == AGORA
    assert ListaZbr.carregar(tmp_path / "nao_existe.json") is None


def test_filtrar_zbr():
    assert filtrar_zbr(["zbrcoord", "Z_OUTRA", " ZBRCOORD ", "", None, "ZBRFIN"]) == ("ZBRCOORD", "ZBRFIN")


def test_resolver_pela_lista_recente_sem_ir_ao_o97():
    fonte = FonteZbrFalsa({"L7654321": ("ZBROUTRO",)})
    lista = ListaZbr(AGORA - timedelta(days=6), {"L7654321": ("ZBRCOORD",)})
    assert resolver_zbr("l7654321", lista, fonte, AGORA) == ("ZBRCOORD",)
    assert fonte.consultas == []


def test_resolver_vai_ao_o97_se_lista_velha_ou_sem_o_igg():
    fonte = FonteZbrFalsa({"L7654321": ("ZBRNOVO", "SAP_X")})
    velha = ListaZbr(AGORA - timedelta(days=9), {"L7654321": ("ZBRCOORD",)})
    assert resolver_zbr("L7654321", velha, fonte, AGORA) == ("ZBRNOVO",)
    sem_igg = ListaZbr(AGORA, {})
    assert resolver_zbr("L7654321", sem_igg, fonte, AGORA) == ("ZBRNOVO",)
    assert resolver_zbr("L7654321", None, fonte, AGORA) == ("ZBRNOVO",)
    assert fonte.consultas == ["L7654321"] * 3


def test_resolver_sem_fonte_nao_chuta():
    assert resolver_zbr("L7654321", None, None, AGORA) is None
    assert resolver_zbr("L7654321", ListaZbr(AGORA - timedelta(days=30), {"L7654321": ("ZBRA",)}), None, AGORA) is None


def test_manifesto(tmp_path):
    caminho = tmp_path / "estado.json"
    m = Manifesto(caminho)
    assert m.adicionar(Entrada("42", "a.json", tipo="criacao", igg="L1234567"))
    assert not m.adicionar(Entrada("42", "copia.json")), "o mesmo envio nunca entra duas vezes"
    m.adicionar(Entrada("43", "b.json", fase=Fase.CONCLUIDA))
    m.salvar()
    m2 = Manifesto(caminho)
    assert m2.conhece_arquivo("a.json") and not m2.conhece_arquivo("copia.json")
    assert [e.chave for e in m2.pendentes()] == ["42"]
    assert m2.entradas["43"].final and m2.entradas["43"].fase is Fase.CONCLUIDA
