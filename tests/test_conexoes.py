"""Falha ao conectar no GRC para a rodada (SessaoParada) uma vez só, sem reabrir o Playwright (visto ao vivo em 23/11/2026:
connect_over_cdp travou 180 s e as simulações seguintes tentaram abrir o Playwright de novo)."""
import pytest

from gestao_usuarios.conexoes import ConexoesReais
from gestao_usuarios.erros import SessaoParada


def test_falha_de_conexao_vira_sessao_parada_e_nao_repete(monkeypatch):
    c = ConexoesReais({"grc": {"cdp": "http://127.0.0.1:9222", "url": "x"}})
    tentativas = []

    def abrir():
        tentativas.append(1)
        raise TimeoutError("BrowserType.connect_over_cdp: Timeout 60000ms exceeded.\nCall log: ...")

    monkeypatch.setattr(c, "_abrir_grc", abrir)
    with pytest.raises(SessaoParada, match="GRC indisponível .*Timeout 60000ms"):
        c.grc_risco()
    with pytest.raises(SessaoParada):
        c.grc_risco()
    assert len(tentativas) == 1


def test_sessao_expirada_tambem_nao_repete(monkeypatch):
    c = ConexoesReais({"grc": {}})
    tentativas = []

    def abrir():
        tentativas.append(1)
        raise SessaoParada("sessão do GRC expirada")

    monkeypatch.setattr(c, "_abrir_grc", abrir)
    for _ in range(2):
        with pytest.raises(SessaoParada, match="expirada"):
            c.grc_risco()
    assert len(tentativas) == 1


class _PaginaFalsa:
    """Página cujo login 'vence' depois de `entra_em` esperas."""
    def __init__(self, entra_em):
        self.restam, self.esperas = entra_em, 0

    def wait_for_timeout(self, ms):
        self.esperas += 1
        self.restam -= 1


def test_esperar_login_segue_quando_o_analista_entra():
    from gestao_usuarios.conexoes import esperar_login
    p = _PaginaFalsa(entra_em=3)
    assert esperar_login(p, limite_s=60, passo_s=3, expirada=lambda pg: pg.restam > 0) is True
    assert p.esperas == 3


def test_esperar_login_sem_pedido_nao_espera():
    from gestao_usuarios.conexoes import esperar_login
    p = _PaginaFalsa(entra_em=0)
    assert esperar_login(p, limite_s=60, expirada=lambda pg: False) is True and p.esperas == 0


def test_esperar_login_desiste_no_limite():
    from gestao_usuarios.conexoes import esperar_login
    p = _PaginaFalsa(entra_em=10**6)
    assert esperar_login(p, limite_s=9, passo_s=3, expirada=lambda pg: True) is False
    assert p.esperas == 3
