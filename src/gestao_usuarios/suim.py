"""E1P › SUIM › Roles by Complex Selection Criteria (RSUSR070): transação -> roles. SOMENTE LEITURA.

Caminho gravado pelo analista em 17/11/2026 (Script Recorder) e conferido ao vivo no E1P/010 no mesmo dia:
  SUIM › árvore: expande '02  1      3' e '03  2      1', clica no link '04  2      2'
  › tela 'Roles by Complex Selection Criteria' (programa RSUSR070, transação S_BCE_68001425)
  › Authorization object (ctxtOBJ1) = S_TCODE, Enter › valor (txtVAL101) = <transação>, Enter
  › Execute (F8) › popup 'Information: N roles with missing authorization not displayed' (OK) › grade GRID1
  com AGR_NAME (Role), TYPE_ICON (Type) e AGR_TEXT (Short Role Description).

Achados da inspeção (FB01):
- A busca por S_TCODE devolve **single roles** (TYPE_ICON '@IC\\QSin...'), que é o que a análise usa (decisão do analista,
  17/11/2026). Composite que aparecer é ignorada com aviso; tipo desconhecido para a etapa (não chuta).
- O popup avisa que N roles não aparecem por falta de autorização de quem roda: o resultado pode estar incompleto, e isso
  vai como aviso no relatório.

Antes de digitar, confere o título da tela e o programa; popup só é confirmado se o texto for conhecido.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from . import sap_gui
from .sap_gui import TelaInesperada


@dataclass(frozen=True)
class ConfigSuim:
    arvore: str
    nos_expandir: tuple[str, ...]
    no_relatorio: str
    titulo_selecao: str
    programa: str
    campo_objeto: str
    objeto: str
    campo_valor: str
    grade: str
    coluna_role: str
    coluna_tipo: str
    coluna_descricao: str
    popups_permitidos: tuple[str, ...]

    @classmethod
    def de_config(cls, cfg: dict) -> "ConfigSuim":
        c = cfg["suim"]
        return cls(
            arvore=c["arvore"], nos_expandir=tuple(c["nos_expandir"]), no_relatorio=c["no_relatorio"],
            titulo_selecao=c.get("titulo_selecao") or "", programa=c.get("programa") or "",
            campo_objeto=c["campo_objeto"], objeto=c["objeto"], campo_valor=c["campo_valor"], grade=c["grade"],
            coluna_role=c.get("coluna_role") or "", coluna_tipo=c.get("coluna_tipo") or "",
            coluna_descricao=c.get("coluna_descricao") or "",
            popups_permitidos=tuple(c.get("popups_permitidos") or ()),
        )

    def pendencias(self) -> list[str]:
        """O que ainda não foi confirmado ao vivo (a etapa não roda sem isso)."""
        return [nome for nome, v in (("suim.titulo_selecao", self.titulo_selecao), ("suim.programa", self.programa),
                                     ("suim.coluna_role", self.coluna_role), ("suim.coluna_tipo", self.coluna_tipo))
                if not v]


class TipoRole(StrEnum):
    SINGLE = "single"
    COMPOSITE = "composite"
    DESCONHECIDO = "desconhecido"


@dataclass(frozen=True)
class RoleSuim:
    nome: str
    tipo: TipoRole
    descricao: str = ""


# ------------------------------------------------------------------ funções puras

def texto_confere(obtido: str, esperado: str) -> bool:
    return bool(esperado) and esperado.strip().casefold() in (obtido or "").strip().casefold()


def popup_permitido(texto: str | None, permitidos: tuple[str, ...]) -> bool:
    return bool(texto) and any(texto_confere(texto, p) for p in permitidos)




def com_nome_da_transacao(transacao: str, nomes: tuple[str, ...]) -> tuple[str, ...]:
    """Single roles que levam o nome da transação (Y-BRF-FB01-POST_DOCUMENT para FB01), como palavra inteira: sem letra ou
    número colado. Nenhuma assim -> todas as candidatas (decisão do analista, 23/11/2026: evita análises desnecessárias)."""
    padrao = re.compile(r"(?<![A-Z0-9])" + re.escape(transacao.upper()) + r"(?![A-Z0-9])")
    com_nome = tuple(n for n in nomes if padrao.search(n.upper()))
    return com_nome or nomes


def tipo_do_icone(icone: str) -> TipoRole:
    """TYPE_ICON do ALV: '@IC\\QSingle Role@' (truncado como '@IC\\QSin'). O texto depois de '\\Q' é a dica do ícone."""
    dica = (icone or "").partition("\\Q")[2].strip().casefold()
    if dica.startswith("sin"):
        return TipoRole.SINGLE
    if dica.startswith("com"):
        return TipoRole.COMPOSITE
    return TipoRole.DESCONHECIDO


def extrair_roles(linhas: list[dict[str, str]], c: ConfigSuim) -> tuple[RoleSuim, ...]:
    """Roles distintas, em ordem alfabética. Coluna ausente no resultado = tela diferente da mapeada."""
    if linhas:
        faltam = [col for col in (c.coluna_role, c.coluna_tipo) if col not in linhas[0]]
        if faltam:
            raise TelaInesperada(f"a grade não tem a(s) coluna(s) {', '.join(faltam)} (colunas: {', '.join(linhas[0])})")
    roles: dict[str, RoleSuim] = {}
    for l in linhas:
        nome = l.get(c.coluna_role, "").strip().upper()
        if nome and nome not in roles:
            roles[nome] = RoleSuim(nome, tipo_do_icone(l.get(c.coluna_tipo, "")), l.get(c.coluna_descricao, "").strip())
    return tuple(roles[n] for n in sorted(roles))


# ------------------------------------------------------------------ navegação (SAP real)

def abrir_relatorio(sessao, c: ConfigSuim, conferir: bool = True) -> str:
    """Do zero até a tela de seleção. Devolve o título da tela aberta."""
    sap_gui.achar(sessao, "wnd[0]/tbar[0]/okcd").text = "/nSUIM"
    sap_gui.achar(sessao, "wnd[0]").sendVKey(0)
    sap_gui.esperar(sessao)
    arvore = sap_gui.achar(sessao, c.arvore)
    for no in c.nos_expandir:
        arvore.expandNode(no)
    arvore.selectItem(c.no_relatorio, "1")
    arvore.clickLink(c.no_relatorio, "1")
    sap_gui.esperar(sessao)
    titulo, programa = sap_gui.titulo(sessao), str(sessao.Info.Program)
    if conferir:
        if not texto_confere(titulo, c.titulo_selecao):
            raise TelaInesperada(f"a SUIM abriu {titulo!r}, esperava {c.titulo_selecao!r}")
        if programa.upper() != c.programa.upper():
            raise TelaInesperada(f"o programa aberto é {programa!r}, esperava {c.programa!r}")
    return titulo


def executar_busca(sessao, c: ConfigSuim, transacao: str, conferir: bool = True) -> tuple[str | None, object]:
    """Preenche S_TCODE = transação, executa e devolve (texto do popup, se houve; grade)."""
    sap_gui.achar(sessao, c.campo_objeto).text = c.objeto
    sap_gui.achar(sessao, "wnd[0]").sendVKey(0)
    sap_gui.esperar(sessao)
    sap_gui.achar(sessao, c.campo_valor).text = transacao
    sap_gui.achar(sessao, "wnd[0]").sendVKey(0)
    sap_gui.esperar(sessao)
    if sap_gui.achar(sessao, c.campo_valor).text.strip().upper() != transacao.upper():
        raise TelaInesperada(f"o valor da transação não ficou {transacao!r}")
    sap_gui.achar(sessao, "wnd[0]/tbar[1]/btn[8]").press()
    sap_gui.esperar(sessao)
    popup = sap_gui.texto_do_popup(sessao)
    if popup is not None:
        if conferir and not popup_permitido(popup, c.popups_permitidos):
            raise TelaInesperada(f"popup não mapeado depois de executar: {popup!r}")
        sap_gui.achar(sessao, "wnd[1]/tbar[0]/btn[0]").press()
        sap_gui.esperar(sessao)
    return popup, sap_gui.achar(sessao, c.grade)


class SuimRoles:
    """Parte da porta SapE1P. Usa uma sessão já aberta (sap_gui.SessaoPropria). `avisos` acumula o que vai ao relatório."""

    def __init__(self, sessao, c: ConfigSuim):
        faltam = c.pendencias()
        if faltam:
            raise TelaInesperada(f"SUIM ainda não confirmada ao vivo: preencher {', '.join(faltam)} "
                                 "(rodar scripts/inspecionar_suim.py)")
        self.sessao, self.c = sessao, c
        self.avisos: list[str] = []

    def roles_por_transacao(self, transacao: str) -> tuple[RoleSuim, ...]:
        abrir_relatorio(self.sessao, self.c)
        _, grade = executar_busca(self.sessao, self.c, transacao)
        _, linhas = sap_gui.ler_grade(grade)
        return extrair_roles(linhas, self.c)

    def singles_por_transacao(self, transacao: str) -> tuple[str, ...]:
        roles = self.roles_por_transacao(transacao)
        desconhecidas = [r.nome for r in roles if r.tipo is TipoRole.DESCONHECIDO]
        if desconhecidas:
            raise TelaInesperada(f"{transacao}: tipo de role não reconhecido na SUIM ({', '.join(desconhecidas)})")
        composites = [r.nome for r in roles if r.tipo is TipoRole.COMPOSITE]
        if composites:
            self.avisos.append(f"SUIM ({transacao}): composites ignoradas, a análise usa só single roles: "
                               f"{', '.join(composites)}")
        singles = tuple(r.nome for r in roles if r.tipo is TipoRole.SINGLE)
        escolhidas = com_nome_da_transacao(transacao, singles)
        if len(escolhidas) < len(singles):
            self.avisos.append(f"SUIM ({transacao}): analisadas só as {len(escolhidas)} single roles com {transacao.upper()} "
                               f"no nome; {len(singles) - len(escolhidas)} outras ignoradas")
        return escolhidas
