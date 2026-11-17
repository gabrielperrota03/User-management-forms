import json

import pytest

from gestao_usuarios.resposta import RespostaInvalida, Tipo, ler_resposta, ler_tipo, separar_transacoes
from gestao_usuarios.seguranca import RegrasSeguranca, avaliar_solicitacao

from .conftest import resposta, solicitacao

REGRAS = RegrasSeguranca(igg_protegidos=frozenset({"L1170904"}))


@pytest.mark.parametrize("texto,tipo", [("Criação de usuário", Tipo.CRIACAO), ("criacao", Tipo.CRIACAO),
                                        ("Modificação de acesso", Tipo.MODIFICACAO), (" MODIFICACAO ", Tipo.MODIFICACAO)])
def test_tipo(texto, tipo):
    assert ler_tipo(texto) is tipo


@pytest.mark.parametrize("texto", ["", None, "Exclusão", 3])
def test_tipo_desconhecido(texto):
    with pytest.raises(RespostaInvalida):
        ler_tipo(texto)


def test_transacoes_separadas_em_maiusculas_sem_repeticao():
    assert separar_transacoes("fb01, FB02;fb01\n me21n  /n") == ("FB01", "FB02", "ME21N", "/N")
    assert separar_transacoes(None) == ()


def test_ler_resposta(tmp_path):
    arq = tmp_path / "r.json"
    arq.write_text(json.dumps(resposta(tipo="Criação de usuário", usuario_referencia="l7654321")), encoding="utf-8-sig")
    s = ler_resposta(arq)
    assert s.tipo is Tipo.CRIACAO and s.usuario_referencia == "L7654321" and s.transacoes == ("FB01", "FB02")


def test_referencia_ignorada_na_modificacao():
    assert solicitacao(usuario_referencia="L7654321").usuario_referencia is None


@pytest.mark.parametrize("conteudo", ["{", "[]", json.dumps({"tipo": "criacao"})])
def test_json_invalido(tmp_path, conteudo):
    arq = tmp_path / "r.json"
    arq.write_text(conteudo, encoding="utf-8")
    with pytest.raises(RespostaInvalida):
        ler_resposta(arq)


def test_solicitacao_valida():
    assert avaliar_solicitacao(solicitacao(), REGRAS) == []
    assert avaliar_solicitacao(solicitacao(solicitante_email="a@external.totalenergies.com"), REGRAS) == []


@pytest.mark.parametrize("campos,trecho", [
    ({"solicitante_email": "x@gmail.com"}, "domínios"),
    ({"solicitante_email": "x@evil-totalenergies.com"}, "domínios"),
    ({"solicitante_email": "totalenergies.com"}, "domínios"),
    ({"solicitante_email": ""}, "domínios"),
    ({"igg": "L12345"}, "IGG com formato"),
    ({"igg": "L1234567*"}, "IGG com formato"),
    ({"igg": "l1170904"}, "protegido"),
    ({"tipo": "criacao", "usuario_referencia": ""}, "sem usuário de referência"),
    ({"tipo": "criacao", "usuario_referencia": "ZBRCOORD"}, "referência com formato"),
    ({"tipo": "criacao", "usuario_referencia": "L1234567"}, "igual ao próprio"),
    ({"transacoes": ""}, "nenhuma transação"),
    ({"transacoes": ",".join(f"T{i:03d}" for i in range(11))}, "máximo"),
    ({"transacoes": "FB01, S*"}, "transações com formato inválido: S*"),
    ({"transacoes": "1FB"}, "formato inválido"),
    ({"justificativa": "  "}, "justificativa"),
])
def test_guardas(campos, trecho):
    motivos = avaliar_solicitacao(solicitacao(**campos), REGRAS)
    assert any(trecho in m for m in motivos), motivos


def test_regras_de_config():
    r = RegrasSeguranca.de_config({"seguranca": {"igg_protegidos": ["l1111111"], "max_transacoes": 2,
                                                 "dominios_permitidos": ["TotalEnergies.com"]}})
    assert r.igg_protegidos == {"L1111111"} and r.max_transacoes == 2 and r.dominios_permitidos == ("totalenergies.com",)
    assert RegrasSeguranca.de_config({}) == RegrasSeguranca()
