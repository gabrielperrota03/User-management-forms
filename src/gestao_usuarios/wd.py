"""Ações genéricas em telas Web Dynpro do GRC (NWBC) pelo Chromium dedicado (Playwright + CDP).

Os ids 'WD..' mudam a cada renderização: os elementos são achados pelo tipo de controle (atributo 'ct') + texto/título,
como no sox-automation. Nenhuma função clica em botão da lista PROIBIDOS (gravam ou alteram algo no GRC).
"""
from __future__ import annotations

import re

from .erros import SessaoParada
from .sap_gui import TelaInesperada

PROIBIDOS = frozenset({
    "save", "save as...", "delete", "submit", "mitigate risk", "mitigate", "remediate", "cancel instance",
    "run in background", "schedule", "properties...", "administration", "reset", "update firefighter log",
})


class BotaoProibido(RuntimeError):
    pass


def _exato(texto: str):
    return re.compile(rf"^\s*{re.escape(texto)}\s*$")


def aguardar(pagina, frame, minimo_ms: int = 1000, maximo_ms: int = 180000) -> None:
    """Espera o indicador de ocupado do Web Dynpro sumir."""
    pagina.wait_for_timeout(minimo_ms)
    decorrido = minimo_ms
    while decorrido < maximo_ms:
        ocupado = frame.evaluate(
            "() => [...document.querySelectorAll('[ct=BI], .urBusyIndicator, .lsBusyIndicator')]"
            ".some(e => e.getBoundingClientRect().height > 0 && getComputedStyle(e).display !== 'none')")
        if not ocupado:
            return
        pagina.wait_for_timeout(500)
        decorrido += 500
    raise TelaInesperada("o GRC não respondeu a tempo")


def conferir_sessao(pagina, frame) -> None:
    if "login.microsoft" in pagina.url:
        raise SessaoParada("o GRC pediu login (SSO): entre na janela do Chromium dedicado")
    texto = frame.evaluate("() => (document.body && document.body.innerText || '')")
    if re.search(r"session.*(expired|timed out|terminated)|has expired", texto, re.I):
        raise SessaoParada("sessão do GRC expirada: entre na janela do Chromium dedicado")


def _visivel(frame, seletor: str, texto: str):
    """Elemento visível com o ct do seletor e o innerText exato (has_text do Playwright inclui textos ocultos)."""
    ident = frame.evaluate(
        "([sel, t]) => { const e = [...document.querySelectorAll(sel)].find(x => (x.innerText || '').trim() === t"
        " && x.getBoundingClientRect().height > 0); return e ? e.id : null; }", [seletor, texto])
    if not ident:
        raise TelaInesperada(f"{texto!r} não encontrado na tela")
    return frame.locator(f"#{ident}")


def clicar_botao(pagina, frame, texto: str, espera_ms: int = 1500) -> None:
    if texto.strip().casefold() in PROIBIDOS:
        raise BotaoProibido(f"a automação não clica em {texto!r}")
    _visivel(frame, '[ct="B"]', texto).click()
    aguardar(pagina, frame, espera_ms)


def clicar_aba(pagina, frame, texto: str) -> None:
    _visivel(frame, '[ct^="TSITM"]', texto).click()
    aguardar(pagina, frame, 1500)


def digitar(pagina, frame, campo, texto: str) -> None:
    """Como um usuário: o Web Dynpro só registra o valor com teclado + saída do campo."""
    campo.click()
    pagina.keyboard.press("Control+A")
    pagina.keyboard.type(texto)
    pagina.keyboard.press("Tab")
    aguardar(pagina, frame, 1200)
    obtido = campo.input_value().strip()
    if obtido.upper() != texto.strip().upper():
        raise TelaInesperada(f"o campo ficou {obtido!r}, esperado {texto!r}")


def opcoes_do_combo(frame, campo) -> tuple[str, list]:
    m = re.search(r"3:'([^']+)'", campo.get_attribute("lsdata") or "")
    if not m:
        raise TelaInesperada("listbox do combo não identificado")
    itens = frame.locator(f"#{m.group(1)}").locator('[ct="LIB_I"]')
    return m.group(1), [itens.nth(i) for i in range(itens.count())]


def textos_do_combo(frame, campo) -> list[str]:
    return [i.inner_text().strip() for i in opcoes_do_combo(frame, campo)[1]]


def escolher(pagina, frame, campo, opcao: str) -> None:
    """Abre o combo com um clique e escolhe a opção pelo texto exato; confere o valor que ficou."""
    if campo.input_value().strip() == opcao:
        return
    campo.click()
    pagina.wait_for_timeout(1200)
    itens = [i for i in opcoes_do_combo(frame, campo)[1] if i.inner_text().strip() == opcao]
    if len(itens) != 1:
        pagina.keyboard.press("Escape")
        raise TelaInesperada(f"opção {opcao!r} não encontrada (ou repetida) no combo")
    itens[0].click()
    aguardar(pagina, frame, 1500)
    if campo.input_value().strip() != opcao:
        raise TelaInesperada(f"o combo ficou {campo.input_value()!r}, esperado {opcao!r}")


def campo_do_criterio(frame, nome: str):
    """Campo de valor da linha de critério cujo campo é `nome` (ex.: 'System', 'User')."""
    ident = frame.evaluate(
        "(nome) => { const c = [...document.querySelectorAll('input[title=\"Choose the field of this criterion\"]')]"
        ".find(e => e.value.trim() === nome && e.getBoundingClientRect().height > 0); if (!c) return null;"
        " const v = [...c.closest('tr').querySelectorAll('input')].filter(e => e !== c"
        " && e.title !== 'Choose the operator of this criterion'); return v.length ? v[v.length - 1].id : null; }", nome)
    if not ident:
        raise TelaInesperada(f"critério {nome!r} não encontrado")
    return frame.locator(f"#{ident}")


def caixa_marcada(frame, rotulo: str) -> bool:
    """Caixa de seleção (span ct=C_standards) pelo rótulo: classe 'lsCheckBox--checked' / '--unchecked' (conferido ao vivo)."""
    classe = frame.evaluate(
        "(t) => { const e = [...document.querySelectorAll('span[ct=\"C_standards\"]')].find(x => (x.innerText||'').trim() === t"
        " && x.getBoundingClientRect().height > 0); return e ? e.className : null; }", rotulo)
    return estado_da_caixa(classe, rotulo)


def estado_da_caixa(classe: str | None, rotulo: str) -> bool:
    if classe is None:
        raise TelaInesperada(f"caixa {rotulo!r} não encontrada")
    tokens = classe.split()
    if "lsCheckBox--checked" in tokens:
        return True
    if "lsCheckBox--unchecked" in tokens:
        return False
    raise TelaInesperada(f"estado da caixa {rotulo!r} não reconhecido ({classe!r})")


def marcar(pagina, frame, rotulo: str, valor: bool) -> None:
    if caixa_marcada(frame, rotulo) != valor:
        _visivel(frame, 'span[ct="C_standards"]', rotulo).click()
        aguardar(pagina, frame, 1500)
    if caixa_marcada(frame, rotulo) != valor:
        raise TelaInesperada(f"a caixa {rotulo!r} não ficou {'marcada' if valor else 'desmarcada'}")


JS_TABELA = r"""(cabecalho) => {
  const th = [...document.querySelectorAll('th')].find(e => (e.innerText||'').trim() === cabecalho && e.getBoundingClientRect().height > 0);
  if (!th) return null;
  const cab = th.closest('tr');
  const nomes = [...cab.children].map(c => (c.innerText||'').trim());
  const linhas = [];
  for (let tr = cab.nextElementSibling; tr; tr = tr.nextElementSibling) {
    const cel = [...tr.children];
    if (cel.length !== nomes.length) continue;
    const reg = {}; cel.forEach((c, i) => { if (nomes[i]) reg[nomes[i]] = (c.innerText||'').trim(); });
    linhas.push(reg);
  }
  const tabela = cab.closest('[ct="ST"]');
  return {colunas: nomes.filter(n => n), linhas, lsdata: tabela ? (tabela.getAttribute('lsdata') || '') : ''};
}"""


def ler_tabela(frame, cabecalho: str) -> dict:
    """{colunas, linhas (só as preenchidas), total (lsdata chave 2)} da tabela que tem a coluna `cabecalho`."""
    t = frame.evaluate(JS_TABELA, cabecalho)
    if t is None:
        raise TelaInesperada(f"tabela com a coluna {cabecalho!r} não encontrada")
    m = re.search(r"\b2:(\d+)", t["lsdata"])
    t["total"] = int(m.group(1)) if m else None
    t["linhas"] = [l for l in t["linhas"] if any(v for v in l.values())]
    return t
