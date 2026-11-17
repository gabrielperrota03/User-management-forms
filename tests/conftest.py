from __future__ import annotations

import pytest

from gestao_usuarios.analise import Risco
from gestao_usuarios.decisao import UsuarioSap
from gestao_usuarios.resposta import de_dict


def resposta(**extra) -> dict:
    base = {
        "id_resposta": "42",
        "enviado_em": "2026-11-17T10:00:00Z",
        "solicitante_nome": "Fulano de Tal",
        "solicitante_email": "fulano.tal@totalenergies.com",
        "tipo": "Modificação de acesso",
        "igg": "L1234567",
        "usuario_referencia": "",
        "transacoes": "FB01, FB02",
        "justificativa": "Lançamentos contábeis",
    }
    base.update(extra)
    return base


def solicitacao(**extra):
    return de_dict(resposta(**extra), "resp.json")


class SapFalso:
    def __init__(self, usuarios: dict[str, UsuarioSap] | None = None, composites: dict[str, tuple[str, ...]] | None = None,
                 depois_da_primeira_leitura: dict[str, UsuarioSap] | None = None):
        self.usuarios = usuarios or {}
        self.composites = composites or {}
        self.depois = depois_da_primeira_leitura or {}
        self.lidos: list[str] = []

    def usuario(self, igg):
        ja_lido = igg in self.lidos
        self.lidos.append(igg)
        if ja_lido and igg in self.depois:
            return self.depois[igg]
        return self.usuarios.get(igg, UsuarioSap(existe=False))

    def composites_por_transacao(self, t):
        return self.composites.get(t, ())


class GrcRiscoFalso:
    def __init__(self, riscos: dict[str, tuple[Risco, ...]] | None = None, falhar: set[str] | None = None):
        self.riscos = riscos or {}
        self.falhar = falhar or set()
        self.simulados: list[tuple[str, str]] = []

    def simular(self, usuario, composite):
        self.simulados.append((usuario, composite))
        if composite in self.falhar:
            raise RuntimeError("tela inesperada")
        return self.riscos.get(composite, ())


class GrcRequestFalso:
    def __init__(self):
        self.criadas: list[tuple[str, str, str]] = []

    def criar_usuario(self, igg, zbr, descricao):
        self.criadas.append((igg, zbr, descricao))
        return "700001"


class FonteZbrFalsa:
    def __init__(self, zbrs: dict[str, tuple[str, ...]]):
        self.zbrs = zbrs
        self.consultas: list[str] = []

    def zbrs_de(self, igg):
        self.consultas.append(igg)
        return self.zbrs.get(igg, ())


@pytest.fixture
def risco_alto():
    return Risco("F001", "Criar e pagar fornecedor", "High")
