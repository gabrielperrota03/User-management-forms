"""O97 (GRC) › User x Business Roles Report (transação Z_USER_BR): IGG -> ZBR. SOMENTE LEITURA.

Mapeado ao vivo em 19/11/2026 (sessão própria no '001 - O97 : GRC : Production', client 960):
  Menu do usuário › 'User x Business Roles Report' = SAP Query, programa 'AQZZZGRCREPORTS=Z_USER_BR', transação Z_USER_BR.
  Tela de seleção: User ID (txtSP$00001-LOW), User Group (txtSP$00004-LOW), Role Name (txtSP$00003-LOW),
  Connector Id (ctxtSP$00002-LOW); saída SAP List Viewer. Execute (F8) › grade GRID1 com as colunas
  GRACUSERROLE-USER_ID, GRACUSER-FIRST_NAME/LAST_NAME, GRACUSERCONN-USER_GROUP, GRACROLE-ROLE_NAME (Business Role),
  GRACROLET-DESCN, TEXT_GRACROLE_ROLE_TYPE, GRACUSERROLE-VALID_FROM/VALID_TO ('dd.mm.aaaa hh:mm:ss').
Achados:
- Sem o Connector Id, um usuário traz também as business roles de BW (ZBRCO_KEYUSER, ZBR_COORD...). Com
  Connector Id = E1PCLNT010 sobra só o ZBR do E1P (ex.: L1170904 -> ZBRCOORD).
- A filial é só a BR-TEP (regra do analista, 19/11/2026): User Group = BR-TEP sempre. BR-TEP + E1PCLNT010 = 229 usuários,
  1 ZBR cada, 9 s.
- A última linha da grade é a de totais do ALV (sem User ID; status 'Valid To cannot be totalled'): é ignorada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from . import sap_gui
from .sap_gui import TelaInesperada
from .zbr import ListaZbr

COL_USER, COL_GRUPO, COL_ROLE = "GRACUSERROLE-USER_ID", "GRACUSERCONN-USER_GROUP", "GRACROLE-ROLE_NAME"
COL_TIPO, COL_DE, COL_ATE = "TEXT_GRACROLE_ROLE_TYPE", "GRACUSERROLE-VALID_FROM", "GRACUSERROLE-VALID_TO"


@dataclass(frozen=True)
class ConfigO97:
    entrada_logon: str = "001 - O97 : GRC : Production"
    transacao: str = "Z_USER_BR"
    programa: str = "AQZZZGRCREPORTS=Z_USER_BR"
    titulo: str = "User x Business Roles Report"
    campo_usuario: str = "wnd[0]/usr/txtSP$00001-LOW"
    campo_grupo: str = "wnd[0]/usr/txtSP$00004-LOW"
    campo_role: str = "wnd[0]/usr/txtSP$00003-LOW"
    campo_connector: str = "wnd[0]/usr/ctxtSP$00002-LOW"
    grade: str = "wnd[0]/usr/cntlGRID1/shellcont/shell"
    user_group: str = "BR-TEP"
    connector: str = "E1PCLNT010"
    tipo_role: str = "Business Role"

    @classmethod
    def de_config(cls, cfg: dict) -> "ConfigO97":
        c = dict(cfg.get("o97") or {})
        if cfg.get("sap", {}).get("conexao_o97"):
            c.setdefault("entrada_logon", cfg["sap"]["conexao_o97"])
        return cls(**{k: v for k, v in c.items() if k in cls.__dataclass_fields__})


# ------------------------------------------------------------------ funções puras

def _data(texto: str) -> date:
    try:
        return datetime.strptime((texto or "").strip()[:10], "%d.%m.%Y").date()
    except ValueError as e:
        raise TelaInesperada(f"data do report do O97 não reconhecida: {texto!r}") from e


def interpretar_linhas(linhas: list[dict[str, str]], c: ConfigO97, hoje: date) -> dict[str, tuple[str, ...]]:
    """Linhas da grade -> {IGG: ZBRs vigentes hoje}. Ignora a linha de totais (sem User ID).
    Linha de outro grupo, outro tipo de role ou coluna faltando = tela diferente da mapeada (não chuta)."""
    if linhas:
        faltam = [x for x in (COL_USER, COL_GRUPO, COL_ROLE, COL_TIPO, COL_DE, COL_ATE) if x not in linhas[0]]
        if faltam:
            raise TelaInesperada(f"o report do O97 não tem as colunas {', '.join(faltam)}")
    por_igg: dict[str, set[str]] = {}
    for l in linhas:
        igg = l[COL_USER].strip().upper()
        if not igg:
            continue                                            # linha de totais do ALV
        if l[COL_GRUPO].strip() != c.user_group:
            raise TelaInesperada(f"o report trouxe {igg} do grupo {l[COL_GRUPO]!r}: esperado só {c.user_group}")
        if l[COL_TIPO].strip() != c.tipo_role:
            raise TelaInesperada(f"o report trouxe uma role do tipo {l[COL_TIPO]!r} para {igg}")
        if _data(l[COL_DE]) <= hoje <= _data(l[COL_ATE]):
            por_igg.setdefault(igg, set()).add(l[COL_ROLE].strip().upper())
        else:
            por_igg.setdefault(igg, set())                      # usuário existe, mas sem ZBR vigente
    return {igg: tuple(sorted(r)) for igg, r in por_igg.items()}


def programa_confere(obtido: str, esperado: str) -> bool:
    """O SAP Query devolve o nome com '=' de preenchimento no fim ('AQZZZGRCREPORTS=Z_USER_BR=====')."""
    return bool(esperado) and obtido.strip().rstrip("=").upper() == esperado.strip().rstrip("=").upper()


def lista_plausivel(nova: dict[str, tuple[str, ...]], antiga: ListaZbr | None, fracao_minima: float = 0.8) -> str | None:
    """Antes de trocar a lista semanal: a extração nova não pode ter encolhido demais (report filtrado por engano, sessão
    caída no meio). Devolve o motivo da recusa, ou None se pode gravar."""
    if not nova:
        return "a extração do O97 veio vazia"
    if antiga is not None and antiga.usuarios and len(nova) < fracao_minima * len(antiga.usuarios):
        return (f"a extração do O97 tem {len(nova)} usuários e a lista atual {len(antiga.usuarios)}: "
                f"menos de {fracao_minima:.0%}, a lista atual foi mantida")
    return None


# ------------------------------------------------------------------ SAP real

def executar_report(sessao, c: ConfigO97, igg: str = "") -> list[dict[str, str]]:
    """Abre Z_USER_BR, preenche User ID (vazio = todos), User Group e Connector, executa e lê a grade inteira."""
    sap_gui.achar(sessao, "wnd[0]/tbar[0]/okcd").text = f"/n{c.transacao}"
    sap_gui.achar(sessao, "wnd[0]").sendVKey(0)
    sap_gui.esperar(sessao)
    programa, titulo = str(sessao.Info.Program), sap_gui.titulo(sessao)
    if not programa_confere(programa, c.programa) or c.titulo.casefold() not in titulo.casefold():
        raise TelaInesperada(f"Z_USER_BR abriu {programa!r} / {titulo!r}")
    valores = {c.campo_usuario: igg.upper(), c.campo_grupo: c.user_group, c.campo_role: "", c.campo_connector: c.connector}
    for campo, valor in valores.items():
        sap_gui.achar(sessao, campo).text = valor
    for campo, valor in valores.items():
        if sap_gui.achar(sessao, campo).text.strip().upper() != valor.upper():
            raise TelaInesperada(f"o campo {campo} ficou {sap_gui.achar(sessao, campo).text!r}, esperado {valor!r}")
    sap_gui.achar(sessao, "wnd[0]/tbar[1]/btn[8]").press()
    sap_gui.esperar(sessao)
    popup = sap_gui.texto_do_popup(sessao)
    if popup is not None:
        raise TelaInesperada(f"popup inesperado no report do O97: {popup!r}")
    try:
        grade = sessao.findById(c.grade)
    except Exception:  # noqa: BLE001 - sem grade: nenhum resultado (a barra de status diz)
        status = ""
        try:
            status = str(sessao.findById("wnd[0]/sbar").Text)
        except Exception:  # noqa: BLE001
            pass
        if programa_confere(str(sessao.Info.Program), c.programa):
            return []                                            # continuou na seleção: nada encontrado
        raise TelaInesperada(f"o report do O97 não mostrou a grade ({status!r})")
    _, linhas = sap_gui.ler_grade(grade)
    return linhas


class FonteZbrO97:
    """Porta FonteZbr (um IGG) e a extração semanal (todos da BR-TEP). Abre a sessão própria sob demanda."""

    def __init__(self, c: ConfigO97, hoje: date | None = None):
        self.c, self.hoje = c, hoje or date.today()

    def _rodar(self, igg: str = "") -> dict[str, tuple[str, ...]]:
        with sap_gui.SessaoPropria("O97", self.c.entrada_logon) as s:
            return interpretar_linhas(executar_report(s, self.c, igg), self.c, self.hoje)

    def zbrs_de(self, igg: str) -> tuple[str, ...]:
        return self._rodar(igg).get(igg.upper(), ())

    def extrair_todos(self) -> dict[str, tuple[str, ...]]:
        return self._rodar("")


def atualizar_lista(extraidos: dict[str, tuple[str, ...]], caminho, agora: datetime) -> tuple[bool, str]:
    """Troca a lista semanal pela extração nova, se for plausível. Devolve (gravou?, mensagem)."""
    antiga = ListaZbr.carregar(caminho)
    motivo = lista_plausivel(extraidos, antiga)
    if motivo:
        return False, motivo
    ListaZbr(agora, extraidos).salvar(caminho)
    sem_zbr = sum(1 for z in extraidos.values() if not z)
    varios = sum(1 for z in extraidos.values() if len(z) > 1)
    return True, f"{len(extraidos)} usuários gravados ({sem_zbr} sem ZBR vigente, {varios} com mais de um)"
