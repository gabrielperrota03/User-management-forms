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
