"""GRC › Access Management › User Level Simulation: riscos do usuário + uma single role. SOMENTE LEITURA.

Mapeado ao vivo em 17/11/2026 (Chromium dedicado, GRC O97 client 960):
  Passo 1 'Define Analysis Criteria': critérios System = E1PCLNT010, User = <IGG> e **Rule Set = 'EP - SOD 2019'**
          (regra do analista, 17/11/2026: sempre esse; a tela vem com 'Total Worldwide - Global Rule Set'). Os outros
          (User Type 'Dialog', Format 'Summary'/'Business View', tipos marcados na tela) ficam como vêm.
  Next › Passo 2 'Define Simulation Criteria': caixa 'Risk from Simulation only' MARCADA (só os riscos que a role traz,
          decisão do analista em 17/11/2026) › aba Roles › Add › linha da grade: Role Type 'Technical Role',
          System 'E1P client 010 - Unisol', Role From = <role>, Actions 'Include'.
  Run in Foreground › Passo 3 'Confirmation': grade 'Result' com o combo Type ('Critical Action', 'Permission Level').
          Cada tipo é lido à parte. 'No Violations' na coluna Action = sem risco naquele tipo.
Nada é salvo: sem variante, sem 'Mitigate Risk', sem 'Run in Background'. A janela da simulação é fechada no fim.
Exemplo real: L1170904 + Y-BRF-FB01-POST_DOCUMENT -> Permission Level: SF028_EP (Medium, FB01, EP_FIN).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from . import wd
from .capturas import capturar_pagina
from .analise import Risco
from .sap_gui import TelaInesperada

log = logging.getLogger(__name__)

TITULO_PASSO = "Simulation: User Level, Step {n}"
# Escolher uma variante salva troca o rótulo do assistente para "Risk Analysis :" (os passos e a tela seguem os da simulação;
# visto ao vivo em 25/11/2026). Só vale com a variante escolhida, e o passo 2 ainda confere o bloco "Simulation Criteria".
TITULO_PASSO_VARIANTE = "Risk Analysis : User Level, Step {n}"
COL_RISCO, COL_DESCRICAO, COL_NIVEL, COL_ACAO = "Access Risk ID", "Risk Description", "Risk Level", "Action"
SEM_VIOLACAO = "no violations"
CAIXA_SO_SIMULACAO = "Risk from Simulation only"


@dataclass(frozen=True)
class ConfigGrcRisco:
    url: str
    rule_set: str = "EP - SOD 2019"
    somente_simulacao: bool = True          # 'Risk from Simulation only': só os riscos que a role traz (analista, 17/11/2026)
    sistema_criterio: str = "E1PCLNT010"
    sistema_simulacao: str = "E1P client 010 - Unisol"
    tipo_role: str = "Technical Role"
    acao: str = "Include"
    aba: str = "Access Management"
    link: str = "User Level Simulation"
    variante: str = "EP_SOD_2019_BRTEP"     # variante salva uma vez no GRC (analista, 25/11/2026); vazio = preenche tudo à mão

    @classmethod
    def de_config(cls, cfg: dict) -> "ConfigGrcRisco":
        c = cfg.get("grc_risco") or {}
        return cls(url=cfg["grc"]["url"], **{k: v for k, v in c.items() if k in cls.__dataclass_fields__ and k != "url"})


# ------------------------------------------------------------------ funções puras

def riscos_das_linhas(linhas: list[dict[str, str]], tipo: str) -> tuple[Risco, ...]:
    """Linhas da grade -> riscos distintos (por Access Risk ID). 'No Violations' = nenhum risco.
    Linha preenchida sem Access Risk ID e sem 'No Violations' = tela não reconhecida (não vale 'sem risco')."""
    riscos: dict[str, Risco] = {}
    for l in linhas:
        rid = l.get(COL_RISCO, "").strip()
        if not rid:
            if l.get(COL_ACAO, "").strip().casefold() == SEM_VIOLACAO:
                continue
            raise TelaInesperada(f"linha do resultado ({tipo}) sem Access Risk ID: {l}")
        if rid not in riscos:
            riscos[rid] = Risco(rid, l.get(COL_DESCRICAO, "").strip(), l.get(COL_NIVEL, "").strip())
    return tuple(riscos.values())


def conferir_total(total: int | None, lidas: int, tipo: str) -> None:
    """Segunda conferência depois da paginação (wd.ler_tabela): lidas tem de bater com o total. Não finge que leu tudo."""
    if total is None:
        raise TelaInesperada(f"total de linhas do resultado ({tipo}) não identificado")
    if total != lidas:
        raise TelaInesperada(f"resultado ({tipo}) tem {total} linhas e foram lidas {lidas}")


def juntar(por_tipo: dict[str, tuple[Risco, ...]]) -> tuple[Risco, ...]:
    """Riscos de todos os tipos, sem repetir o mesmo Access Risk ID."""
    vistos: dict[str, Risco] = {}
    for riscos in por_tipo.values():
        for r in riscos:
            vistos.setdefault(r.id, r)
    return tuple(vistos.values())


def criterios_conferem(lidos: dict[str, str], c: ConfigGrcRisco, usuario: str) -> list[str]:
    """Divergências entre a tela do passo 1 e o esperado (vazia = pode seguir). O Rule Set é obrigatório."""
    esperado = {"System": c.sistema_criterio, "User": usuario.upper(), "Rule Set": c.rule_set}
    return [f"{k}: tela {lidos.get(k)!r}, esperado {v!r}" for k, v in esperado.items()
            if (lidos.get(k) or "").strip().upper() != v.upper()]


# ------------------------------------------------------------------ navegação (GRC real)

def conferir_criterios(janela, frame, c: ConfigGrcRisco, usuario: str) -> None:
    lidos = {k: wd.campo_do_criterio(frame, k).input_value() for k in ("System", "User", "Rule Set")}
    divergencias = criterios_conferem(lidos, c, usuario)
    if divergencias:
        raise TelaInesperada("critérios da simulação divergentes: " + "; ".join(divergencias))


def _nwbc(contexto, url: str):
    for pg in contexto.pages:
        if "/ui2/nwbc/" in pg.url and not pg.is_closed():
            return pg
    pg = contexto.new_page()
    pg.goto(url, wait_until="load")
    pg.wait_for_timeout(4000)
    return pg


def _frame_do_service_map(pagina):
    frames = [f for f in pagina.frames if f.name.startswith("iFrameId")]
    if not frames:
        raise TelaInesperada("service map do NWBC não carregou")
    return frames[-1]


def titulo_confere(texto: str, n: int, com_variante: bool = False) -> bool:
    """O cabeçalho do assistente é o do passo `n` da simulação (com variante, também vale o rótulo 'Risk Analysis :')."""
    texto = re.sub(r"\s+", " ", texto or "")
    modelos = (TITULO_PASSO, TITULO_PASSO_VARIANTE) if com_variante else (TITULO_PASSO,)
    return any(m.format(n=n) in texto for m in modelos)


def _esperar_titulo(pagina, frame, n: int, limite_s: int = 120, com_variante: bool = False) -> None:
    esperado = TITULO_PASSO.format(n=n)
    for _ in range(limite_s * 2):
        texto = frame.evaluate("() => (document.body && document.body.innerText || '').slice(0, 300)")
        if titulo_confere(texto, n, com_variante):
            if com_variante and n == 2:                  # com o rótulo trocado, confirma que é a tela da simulação
                corpo = frame.evaluate("() => (document.body && document.body.innerText || '')")
                if "Simulation Criteria" not in corpo:
                    raise TelaInesperada("passo 2 sem o bloco 'Simulation Criteria'")
            return
        pagina.wait_for_timeout(500)
    wd.conferir_sessao(pagina, frame)
    raise TelaInesperada(f"a tela não chegou em {esperado!r}")


def abrir_simulacao(contexto, c: ConfigGrcRisco):
    """NWBC › aba › link 'User Level Simulation' (abre janela nova). Devolve (janela, frame)."""
    nwbc = _nwbc(contexto, c.url)
    if "login.microsoft" in nwbc.url:
        raise wd.SessaoParada("o GRC pediu login (SSO): entre na janela do Chromium dedicado")
    nwbc.get_by_role("link", name=c.aba, exact=True).first.click()
    nwbc.wait_for_timeout(3000)
    sm = _frame_do_service_map(nwbc)
    links = sm.locator('a[ct="LN"]')
    alvo = [links.nth(i) for i in range(links.count()) if links.nth(i).inner_text().strip() == c.link]
    if len(alvo) != 1:
        raise TelaInesperada(f"link {c.link!r} não encontrado (ou repetido) no service map")
    with contexto.expect_page(timeout=60000) as nova:
        alvo[0].click()
    janela = nova.value
    janela.wait_for_load_state("load")
    frame = None
    for _ in range(90):
        frame = janela.frame(name="content_frame")
        if frame is not None and frame.locator('[ct="B"]').count():
            break
        janela.wait_for_timeout(1000)
    if frame is None:
        raise TelaInesperada("a janela da simulação não carregou")
    wd.aguardar(janela, frame, 1500)
    _esperar_titulo(janela, frame, 1)
    return janela, frame


def campo_do_rotulo(frame, rotulo: str):
    """Campo (input) cujo rótulo é `rotulo`, ligado pelo atributo lsdata 29 (ex.: 'Saved Variants', 'Save Variant as')."""
    ident = frame.evaluate(
        "(r) => { const s = [...document.querySelectorAll('span')].find(e => e.id.endsWith('-text')"
        " && (e.innerText || '').replace(/\\s+/g, ' ').trim() === r && e.getBoundingClientRect().height > 0);"
        " if (!s) return null; const lab = s.id.replace('-text', '');"
        " const i = [...document.querySelectorAll('input')].find(e => (e.getAttribute('lsdata') || '').includes(\"29:'\" + lab + \"'\"));"
        " return i ? i.id : null; }", rotulo)
    return frame.locator("#" + ident) if ident else None


def escolher_variante(janela, frame, nome: str) -> bool:
    """Passo 1: escolhe a variante salva (System, Rule Set, tipo do relatório...). False = não existe, segue sem ela (o
    preenchimento manual logo depois confere tudo do mesmo jeito)."""
    if not nome:
        return False
    campo = campo_do_rotulo(frame, "Saved Variants")
    if campo is None:
        log.warning("campo Saved Variants não encontrado; preenchendo os critérios à mão")
        return False
    campo.click()
    janela.wait_for_timeout(1200)
    existentes = wd.textos_do_combo(frame, campo)
    janela.keyboard.press("Escape")
    janela.wait_for_timeout(400)
    if nome not in existentes:
        log.warning("variante %r não existe no GRC (rodar scripts/criar_variante_grc.py); preenchendo à mão", nome)
        return False
    wd.escolher(janela, frame, campo, nome)
    wd.aguardar(janela, frame, 2500)
    return True


def _linha_da_simulacao(frame) -> list:
    """Campos da primeira linha da grade de roles (Role Type, System, Role From, Role To, Actions)."""
    ids = frame.evaluate(
        "() => { const th = [...document.querySelectorAll('th')].find(e => (e.innerText||'').trim() === 'Role Type'"
        " && e.getBoundingClientRect().height > 0); if (!th) return null; const t = th.closest('[ct=\"ST\"]');"
        " return [...t.querySelectorAll('input')].filter(e => e.getBoundingClientRect().height > 0).map(e => e.id); }")
    if not ids or len(ids) < 5:
        raise TelaInesperada(f"linha da simulação de roles não apareceu (campos: {ids})")
    return [frame.locator(f"#{i}") for i in ids[:5]]


def simular(contexto, c: ConfigGrcRisco, usuario: str, role: str, pasta_prints: Path | None = None
            ) -> tuple[dict[str, tuple[Risco, ...]], list[Path]]:
    """Uma simulação completa. Devolve ({tipo: riscos}, prints). A janela aberta aqui é fechada no fim."""
    janela, frame = abrir_simulacao(contexto, c)
    prints: list[Path] = []
    try:
        # passo 1 (a variante já traz System e Rule Set; o preenchimento abaixo vira conferência e `conferir_criterios` valida)
        com_variante = escolher_variante(janela, frame, c.variante)
        wd.digitar(janela, frame, wd.campo_do_criterio(frame, "System"), c.sistema_criterio)
        wd.digitar(janela, frame, wd.campo_do_criterio(frame, "User"), usuario)
        wd.escolher(janela, frame, wd.campo_do_criterio(frame, "Rule Set"), c.rule_set)
        conferir_criterios(janela, frame, c, usuario)
        wd.clicar_botao(janela, frame, "Next")
        _esperar_titulo(janela, frame, 2, com_variante=com_variante)
        # passo 2
        wd.marcar(janela, frame, CAIXA_SO_SIMULACAO, c.somente_simulacao)
        wd.clicar_aba(janela, frame, "Roles")
        wd.clicar_botao(janela, frame, "Add")
        tipo_role, sistema, de, _ate, acao = _linha_da_simulacao(frame)
        wd.escolher(janela, frame, tipo_role, c.tipo_role)
        wd.escolher(janela, frame, sistema, c.sistema_simulacao)
        wd.digitar(janela, frame, de, role)
        wd.escolher(janela, frame, acao, c.acao)
        lidos = [x.input_value().strip() for x in _linha_da_simulacao(frame)]
        if lidos[0] != c.tipo_role or lidos[1] != c.sistema_simulacao or lidos[2].upper() != role.upper() \
                or lidos[4] != c.acao:
            raise TelaInesperada(f"linha da simulação ficou {lidos}")
        if wd.caixa_marcada(frame, CAIXA_SO_SIMULACAO) != c.somente_simulacao:
            raise TelaInesperada(f"a caixa {CAIXA_SO_SIMULACAO!r} mudou antes de rodar")
        wd.clicar_botao(janela, frame, "Run in Foreground", espera_ms=3000)
        _esperar_titulo(janela, frame, 3, limite_s=300, com_variante=com_variante)
        # passo 3: cada tipo do combo Type
        combo = frame.locator("#" + frame.evaluate(
            "() => { const l = [...document.querySelectorAll('label, span')].find(e => (e.innerText||'').trim() === 'Type:'"
            " && e.getBoundingClientRect().height > 0); const c = [...document.querySelectorAll('input[ct^=\"CB\"]')]"
            ".filter(e => e.getBoundingClientRect().height > 0 && ['Critical Action','Permission Level'].includes(e.value));"
            " return c.length ? c[0].id : null; }"))
        por_tipo: dict[str, tuple[Risco, ...]] = {}
        for tipo in wd.textos_do_combo(frame, combo):
            wd.escolher(janela, frame, combo, tipo)

            def tirar_print(tela: int, tipo=tipo) -> None:
                if pasta_prints is None:
                    return
                pasta_prints.mkdir(parents=True, exist_ok=True)
                nome = f"grc_{usuario}_{re.sub(r'[^A-Za-z0-9_-]', '_', role)}_{tipo.replace(' ', '_')}_{tela + 1:02d}.png"
                if capturar_pagina(janela, pasta_prints / nome):         # recortada no conteúdo (capturas.py)
                    prints.append(pasta_prints / nome)

            t = wd.ler_tabela(janela, frame, COL_RISCO, ao_mostrar=tirar_print)
            conferir_total(t["total"], len(t["linhas"]), tipo)
            por_tipo[tipo] = riscos_das_linhas(t["linhas"], tipo)
        if not por_tipo:
            raise TelaInesperada("o combo Type do resultado não tem opções")
        return por_tipo, prints
    finally:
        try:
            janela.close()
        except Exception:  # noqa: BLE001
            log.warning("não consegui fechar a janela da simulação")


class GrcRiscoPlaywright:
    """Porta GrcRisco. `contexto` = contexto do Chromium dedicado já conectado por CDP."""

    def __init__(self, contexto, c: ConfigGrcRisco, pasta_prints: Path | None = None):
        self.contexto, self.c, self.pasta_prints = contexto, c, pasta_prints
        self.prints: list[Path] = []
        self.detalhe: dict[tuple[str, str], dict[str, tuple[Risco, ...]]] = {}

    def simular(self, usuario: str, role: str) -> tuple[Risco, ...]:
        por_tipo, prints = simular(self.contexto, self.c, usuario, role, self.pasta_prints)
        self.prints += prints
        self.detalhe[(usuario, role)] = por_tipo
        return juntar(por_tipo)
