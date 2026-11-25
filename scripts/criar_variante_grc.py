"""Cria UMA VEZ no GRC a variante do passo 1 da simulação (User Level Simulation › Saved Variants).

Autorizado pelo analista em 25/11/2026 como a ÚNICA escrita no GRC além da request de criação (CLAUDE.md, regra 2): grava só a
variante `grc_risco.variante` (System E1PCLNT010, Rule Set EP - SOD 2019, relatório Critical Action + Permission Level).
A rotina nunca clica em Save (wd.PROIBIDOS); só este script, de propósito. Se a variante já existe, não faz nada.

  python scripts/criar_variante_grc.py        (com o Chromium dedicado logado no GRC)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright  # noqa: E402

from gestao_usuarios import config, grc_risco, wd  # noqa: E402


def main() -> int:
    cfg = config.carregar()
    c = grc_risco.ConfigGrcRisco.de_config(cfg)
    if not c.variante:
        print("grc_risco.variante está vazio no config: nada a criar")
        return 3
    with sync_playwright() as p:
        ctx = p.chromium.connect_over_cdp(cfg["grc"]["cdp"], timeout=60000).contexts[0]
        janela, frame = grc_risco.abrir_simulacao(ctx, c)
        try:
            lista = grc_risco.campo_do_rotulo(frame, "Saved Variants")
            lista.click()
            janela.wait_for_timeout(1200)
            if c.variante in wd.textos_do_combo(frame, lista):
                print(f"a variante {c.variante!r} já existe: nada a fazer")
                return 0
            janela.keyboard.press("Escape")
            wd.digitar(janela, frame, wd.campo_do_criterio(frame, "System"), c.sistema_criterio)
            wd.escolher(janela, frame, wd.campo_do_criterio(frame, "Rule Set"), c.rule_set)
            grc_risco.conferir_criterios(janela, frame, c, "")
            nome = grc_risco.campo_do_rotulo(frame, "Save Variant as")
            nome.click()
            janela.keyboard.type(c.variante)
            janela.keyboard.press("Tab")
            janela.wait_for_timeout(800)
            ident = frame.evaluate(
                "() => { const b = [...document.querySelectorAll('[ct=\"B\"]')].filter(e => (e.innerText || '').trim() === 'Save'"
                " && e.getBoundingClientRect().height > 0); return b.length === 1 ? b[0].id : null; }")
            if not ident:
                print("botão Save não encontrado (ou repetido): nada foi salvo")
                return 1
            frame.locator("#" + ident).click()          # o único clique em Save do projeto
            wd.aguardar(janela, frame, 3000)
            lista = grc_risco.campo_do_rotulo(frame, "Saved Variants")
            lista.click()
            janela.wait_for_timeout(1200)
            ok = c.variante in wd.textos_do_combo(frame, lista)
            print("variante criada" if ok else "Save clicado, mas a variante não apareceu na lista", c.variante)
            return 0 if ok else 1
        finally:
            janela.close()


if __name__ == "__main__":
    sys.exit(main())
