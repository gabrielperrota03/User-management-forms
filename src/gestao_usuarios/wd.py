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
    itens = []
    for _ in range(3):                     # às vezes o clique não abre a lista (visto ao vivo no Rule Set, 19/11/2026)
        campo.click()
        pagina.wait_for_timeout(1200)
        itens = [i for i in opcoes_do_combo(frame, campo)[1] if i.inner_text().strip() == opcao]
        if len(itens) == 1 and itens[0].bounding_box():
            break
        pagina.keyboard.press("Escape")
        pagina.wait_for_timeout(800)
    if len(itens) != 1 or not itens[0].bounding_box():
        pagina.keyboard.press("Escape")
        raise TelaInesperada(f"opção {opcao!r} não encontrada (ou repetida, ou a lista não abriu) no combo")
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
  const tabela = cab.closest('[ct="ST"]');
  const linhas = {};
  for (const tr of tabela.querySelectorAll('tr[rr]')) {
    const rr = parseInt(tr.getAttribute('rr'));
    const cel = [...tr.children];
    if (!(rr > 0) || cel.length !== nomes.length) continue;      // rr=0: linha vazia de preenchimento
    const reg = {}; cel.forEach((c, i) => { if (nomes[i]) reg[nomes[i]] = (c.innerText||'').trim(); });
    linhas[rr] = reg;
  }
  const barra = document.getElementById(tabela.id + '-scrollV');
  return {id: tabela.id, colunas: nomes.filter(n => n), linhas, lsdata: tabela.getAttribute('lsdata') || '',
          barra: barra ? (barra.getAttribute('lsdata') || '') : ''};
}"""


def _chave(lsdata: str, chave: int) -> int | None:
    m = re.search(rf"(?:^|[{{,]){chave}:(-?\d+)", lsdata or "")
    return int(m.group(1)) if m else None


def info_tabela(bruto: dict) -> dict:
    """lsdata da tabela: 2 = total de linhas, 5 = linhas por tela. lsdata da barra vertical: 0 = primeira linha na tela."""
    return {"total": _chave(bruto["lsdata"], 2), "por_tela": _chave(bruto["lsdata"], 5),
            "posicao": _chave(bruto["barra"], 0)}


def linhas_faltando(lidas, total: int) -> list[int]:
    """Números de linha (1..total) que ainda não foram lidos."""
    vistos = {int(x) for x in lidas}
    return [i for i in range(1, total + 1) if i not in vistos]


def _ler(frame, cabecalho: str) -> dict:
    bruto = frame.evaluate(JS_TABELA, cabecalho)
    if bruto is None:
        raise TelaInesperada(f"tabela com a coluna {cabecalho!r} não encontrada")
    return bruto


def ler_tabela(pagina, frame, cabecalho: str, ao_mostrar=None, max_telas: int = 300) -> dict:
    """Todas as linhas da tabela que tem a coluna `cabecalho`, tela por tela.

    Cada linha traz no atributo `rr` o número absoluto no resultado (conferido ao vivo). A tabela mostra `por_tela` linhas;
    a roda do mouse sobre ela pede as seguintes ao servidor. Lê até ter 1..total sem buraco, chamando ao_mostrar(n) a cada
    tela (ex.: o print). Devolve {colunas, linhas (na ordem), total}. Sem conseguir ler tudo, levanta TelaInesperada."""
    bruto = _ler(frame, cabecalho)
    info = info_tabela(bruto)
    total = info["total"]
    if total is None:
        raise TelaInesperada(f"total de linhas da tabela {cabecalho!r} não identificado")
    linhas: dict[int, dict] = {}
    for tela in range(max_telas):
        linhas.update({int(k): v for k, v in bruto["linhas"].items()})
        if ao_mostrar is not None:
            ao_mostrar(tela)
        if not linhas_faltando(linhas, total):
            break
        # cada giro da roda anda UMA linha (visto ao vivo em 19/11/2026, qualquer que seja o delta): gira até a primeira linha
        # que falta ficar no topo da tela (ou até o fim da tabela), conferindo a posição a cada giro
        por_tela = info["por_tela"] or 10
        faltante = linhas_faltando(linhas, total)[0]
        alvo = min(faltante, max(total - por_tela + 1, 1))
        caixa = frame.locator(f'#{bruto["id"]}').bounding_box()
        if caixa is None:
            raise TelaInesperada("a tabela do resultado está fora da tela")
        pagina.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + min(caixa["height"] / 2, 200))

        def girar(delta: int) -> None:
            nonlocal bruto, info
            antes = (info["posicao"], tuple(sorted(bruto["linhas"])))
            pagina.mouse.wheel(0, delta)
            for _ in range(60):                              # espera o servidor redesenhar (até ~6 s)
                pagina.wait_for_timeout(100)
                bruto = _ler(frame, cabecalho)
                info = info_tabela(bruto)
                if (info["posicao"], tuple(sorted(bruto["linhas"]))) != antes:
                    return
            raise TelaInesperada(f"a tabela não rolou: faltam as linhas {linhas_faltando(linhas, total)[:10]}...")

        for _ in range(por_tela * 3):                        # desce até o alvo
            if (info["posicao"] or 1) >= alvo:
                break
            girar(100)
        for _ in range(por_tela * 3):                        # passou do alvo (giro de mais de uma linha): volta
            if str(faltante) in bruto["linhas"]:
                break
            girar(-100)
        aguardar(pagina, frame, 300)
        bruto = _ler(frame, cabecalho)
        info = info_tabela(bruto)
    faltam = linhas_faltando(linhas, total)
    if faltam:
        raise TelaInesperada(f"linhas não lidas do resultado: {faltam[:10]}")
    return {"colunas": bruto["colunas"], "linhas": [linhas[i] for i in range(1, total + 1)], "total": total}
