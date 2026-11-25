"""Índice transação -> single roles, a partir da extração da tabela de autorizações das roles (AGR_1251, objeto S_TCODE).

Substitui a SUIM na análise: a extração `ALL single roles X Transactions.XLSX` vira um JSON (`scripts/gerar_indice_roles.py`) que
é consultado na memória. A extração quase não muda (decisão do analista, 25/11/2026): não há atualização automática nem alerta de
idade; a data da extração só fica registrada no índice. Leitor de XLSX só com a biblioteca padrão (sem openpyxl).
Valor com `*` (ex.: YBIR*) vale como prefixo: a role dá acesso a toda transação que casa. Faixa "até" não é expandida (fica nas
ressalvas da geração). Transação que não está no índice = lista vazia + aviso, nunca "sem risco" (regra 4).
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .arquivos import gravar_texto
from .suim import com_nome_da_transacao

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Colunas da extração (por posição, porque o cabeçalho repete nomes): conferidas contra o cabeçalho antes de ler.
COLUNAS = {"A": "Role", "C": "Authorization object", "G": "Authorization value"}
COLUNA_ATE, COLUNA_APAGADO = "H", "J"
OBJETO = "S_TCODE"


FILTRO_AGR_1251 = "OBJECT = 'S_TCODE' AND FIELD = 'TCD' AND AGR_NAME LIKE '{roles}'"
CAMPOS_AGR_1251 = ["AGR_NAME", "OBJECT", "AUTH", "FIELD", "LOW", "HIGH", "DELETED"]


class ExtracaoInvalida(ValueError):
    """A planilha não tem o formato esperado: nada é gerado."""


def ler_xlsx(caminho: Path) -> list[dict[str, str]]:
    """Primeira aba como lista de linhas {coluna: texto} (célula vazia = ''). Só biblioteca padrão."""
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        compartilhadas: list[str] = []
        if "xl/sharedStrings.xml" in nomes:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_NS + "si"):
                compartilhadas.append("".join(t.text or "" for t in si.iter(_NS + "t")))
        aba = "xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in nomes else \
            sorted(n for n in nomes if n.startswith("xl/worksheets/sheet"))[0]
        linhas: list[dict[str, str]] = []
        for r in ET.fromstring(z.read(aba)).find(_NS + "sheetData").findall(_NS + "row"):
            linha: dict[str, str] = {}
            for c in r.findall(_NS + "c"):
                coluna = re.match(r"[A-Z]+", c.get("r") or "").group(0)
                v = c.find(_NS + "v")
                if c.get("t") == "inlineStr":
                    texto = "".join(t.text or "" for t in c.iter(_NS + "t"))
                elif v is None or v.text is None:
                    texto = ""
                elif c.get("t") == "s":
                    texto = compartilhadas[int(v.text)]
                else:
                    texto = v.text
                linha[coluna] = texto.strip()
            linhas.append(linha)
    return linhas


@dataclass
class IndiceRoles:
    gerado_em: datetime                              # data da extração (informativo)
    origem: str
    transacoes: dict[str, tuple[str, ...]]
    avisos: list[str] = field(default_factory=list)  # acumulam para o relatório (a rodada esvazia entre solicitações)

    # --- construção -----------------------------------------------------------------------------------------------
    @classmethod
    def da_extracao(cls, linhas: list[dict[str, str]], origem: str, gerado_em: datetime) -> tuple["IndiceRoles", list[str]]:
        """Devolve (índice, ressalvas). Linhas apagadas (X) saem; faixa 'até' não é expandida: fica nas ressalvas."""
        if not linhas:
            raise ExtracaoInvalida("planilha vazia")
        cab = linhas[0]
        for col, nome in COLUNAS.items():
            if cab.get(col, "").casefold() != nome.casefold():
                raise ExtracaoInvalida(f"coluna {col} é {cab.get(col)!r}, esperado {nome!r}: o formato da extração mudou")
        if not cab.get(COLUNA_APAGADO, "").casefold().startswith("id whether object is deleted"):
            raise ExtracaoInvalida(f"coluna {COLUNA_APAGADO} é {cab.get(COLUNA_APAGADO)!r}: o formato da extração mudou")
        return cls._indexar((
            (i, l.get("C", ""), l.get("A", ""), l.get("G", ""), l.get(COLUNA_ATE, ""), l.get(COLUNA_APAGADO, ""))
            for i, l in enumerate(linhas[1:], start=2)), origem, gerado_em)

    @classmethod
    def da_tabela(cls, linhas: list[dict[str, str]], origem: str, gerado_em: datetime) -> tuple["IndiceRoles", list[str]]:
        """Linhas da AGR_1251 lida por RFC (colunas por nome: AGR_NAME, OBJECT, FIELD, LOW, HIGH, DELETED)."""
        if not linhas:
            raise ExtracaoInvalida("tabela vazia")
        for col in ("AGR_NAME", "OBJECT", "FIELD", "LOW", "HIGH", "DELETED"):
            if col not in linhas[0]:
                raise ExtracaoInvalida(f"a tabela não trouxe a coluna {col}")
        return cls._indexar((
            (i, l["OBJECT"], l["AGR_NAME"], l["LOW"], l["HIGH"], l["DELETED"])
            for i, l in enumerate(linhas, start=1) if l["FIELD"].upper() == "TCD"), origem, gerado_em)

    @classmethod
    def _indexar(cls, registros, origem: str, gerado_em: datetime) -> tuple["IndiceRoles", list[str]]:
        """registros = (nº, objeto, role, valor, até, apagado). Só S_TCODE; apagadas saem; faixa 'até' fica nas ressalvas."""
        mapa: dict[str, set[str]] = {}
        ressalvas: list[str] = []
        for i, objeto, role, valor, ate, apagado in registros:
            if objeto.upper() != OBJETO or apagado.upper() == "X":
                continue
            role, valor = role.upper(), valor.upper()
            if not role or not valor:
                continue
            if ate:
                ressalvas.append(f"linha {i}: {role} tem faixa ({valor!r}..{ate!r}); não expandida")
                continue
            mapa.setdefault(valor, set()).add(role)
        if not mapa:
            raise ExtracaoInvalida("nenhuma linha S_TCODE aproveitável")
        return cls(gerado_em, origem, {t: tuple(sorted(r)) for t, r in sorted(mapa.items())}), ressalvas

    @classmethod
    def do_xlsx(cls, caminho: Path) -> tuple["IndiceRoles", list[str]]:
        gerado = datetime.fromtimestamp(caminho.stat().st_mtime).replace(microsecond=0)
        return cls.da_extracao(ler_xlsx(caminho), caminho.name, gerado)

    # --- arquivo --------------------------------------------------------------------------------------------------
    @classmethod
    def carregar(cls, caminho: Path) -> "IndiceRoles | None":
        if not caminho.exists():
            return None
        d = json.loads(caminho.read_text(encoding="utf-8-sig"))
        return cls(datetime.fromisoformat(d["gerado_em"]), d.get("origem", ""),
                   {k.upper(): tuple(v) for k, v in d["transacoes"].items()})

    def salvar(self, caminho: Path) -> None:
        dados = {"gerado_em": self.gerado_em.isoformat(timespec="seconds"), "origem": self.origem,
                 "total_transacoes": len(self.transacoes),
                 "transacoes": {k: list(v) for k, v in sorted(self.transacoes.items())}}
        gravar_texto(caminho, json.dumps(dados, ensure_ascii=False, indent=1))

    def _roles_de(self, t: str) -> tuple[str, ...]:
        achadas = set(self.transacoes.get(t, ()))
        for padrao, roles in self.transacoes.items():
            if "*" in padrao and re.fullmatch(".*".join(re.escape(x) for x in padrao.split("*")), t):
                achadas.update(roles)
        return tuple(sorted(achadas))

    # --- consulta (a mesma interface da SuimRoles) -------------------------------------------------------------------
    def singles_por_transacao(self, transacao: str) -> tuple[str, ...]:
        t = transacao.strip().upper()
        roles = self._roles_de(t)
        if not roles:
            self.avisos.append(f"{t}: transação não está na tabela de roles (extração de {self.gerado_em:%d/%m/%Y})")
            return ()
        escolhidas = com_nome_da_transacao(t, roles)
        if len(escolhidas) < len(roles):
            self.avisos.append(f"{t}: analisadas só as {len(escolhidas)} single roles com {t} no nome; "
                               f"{len(roles) - len(escolhidas)} outras ignoradas")
        return escolhidas


def comparar_indices(atual: IndiceRoles, novo: IndiceRoles) -> dict[str, list]:
    """Diferenças entre dois índices (ordenadas): transações e roles que só existem de um lado, e transações cujas roles mudam."""
    def roles(i):
        return {r for rs in i.transacoes.values() for r in rs}
    mudaram = sorted(t for t in atual.transacoes.keys() & novo.transacoes.keys() if atual.transacoes[t] != novo.transacoes[t])
    return {"transacoes_so_no_atual": sorted(atual.transacoes.keys() - novo.transacoes.keys()),
            "transacoes_so_no_novo": sorted(novo.transacoes.keys() - atual.transacoes.keys()),
            "roles_so_no_atual": sorted(roles(atual) - roles(novo)), "roles_so_no_novo": sorted(roles(novo) - roles(atual)),
            "transacoes_com_roles_diferentes": mudaram}
