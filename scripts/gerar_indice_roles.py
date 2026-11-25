r"""Gera o índice transação -> single roles (roles_por_transacao.json): da extração XLSX ou direto da AGR_1251 por RFC.

A tabela quase não muda (analista, 25/11/2026): rodar de novo só se alguém refizer a extração. O índice vai para `roles.indice` do
config (7 - Automações/Gestao Usuarios); a planilha, o CSV e o índice não são versionados. Se o índice já existe, mostra as
diferenças e só grava com --gravar (o anterior é guardado como .anterior.json).

  python scripts/gerar_indice_roles.py ["C:/Users/L1170904/Sapworkdir/ALL single roles X Transactions.XLSX"] [--gravar]
  python scripts/gerar_indice_roles.py --rfc [--roles "Y-BR%"] [--gravar]       # lê a AGR_1251 do E1P (RFC, só leitura)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gestao_usuarios import config, rfc_sap  # noqa: E402
from gestao_usuarios.roles import (CAMPOS_AGR_1251, FILTRO_AGR_1251, ExtracaoInvalida, IndiceRoles,  # noqa: E402
                                   comparar_indices)

PADRAO = Path("C:/Users/L1170904/Sapworkdir/ALL single roles X Transactions.XLSX")


def _da_tabela_por_rfc(cfg: dict, roles: str) -> tuple[IndiceRoles, list[str]]:
    r = cfg.get("rfc") or {}
    sistema, mandante = r.get("sistema", "E1P"), str(r.get("mandante", "010"))
    rfc, _ = rfc_sap.conectar_por_sistema(sistema, mandante)
    try:
        linhas = rfc_sap.ler_tabela(rfc, "AGR_1251", CAMPOS_AGR_1251, FILTRO_AGR_1251.format(roles=roles))
    finally:
        rfc.fechar()
    print(f"AGR_1251 ({sistema}/{mandante}, roles {roles!r}): {len(linhas)} linhas")
    return IndiceRoles.da_tabela(linhas, f"AGR_1251 por RFC ({sistema}/{mandante})", datetime.now().replace(microsecond=0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("xlsx", nargs="?", help="extração XLSX (padrão: Sapworkdir)")
    ap.add_argument("--rfc", action="store_true", help="ler a AGR_1251 do SAP por RFC em vez da planilha")
    ap.add_argument("--roles", default="Y-BR%", help="filtro LIKE das roles no modo --rfc (padrão Y-BR%%: só o Brasil, regra 2b)")
    ap.add_argument("--gravar", action="store_true", help="grava mesmo que o índice já exista (guarda o anterior)")
    a = ap.parse_args()
    cfg = config.carregar()
    destino = Path(cfg["roles"]["indice"])
    try:
        novo, ressalvas = _da_tabela_por_rfc(cfg, a.roles) if a.rfc else IndiceRoles.do_xlsx(Path(a.xlsx) if a.xlsx else PADRAO)
    except (OSError, ExtracaoInvalida, rfc_sap.ErroRFC) as e:
        print(f"nada gerado: {e}")
        return 1
    roles = {r for rs in novo.transacoes.values() for r in rs}
    print(f"novo índice: {len(novo.transacoes)} transações, {len(roles)} single roles")
    for r in ressalvas:
        print("ressalva:", r)
    atual = IndiceRoles.carregar(destino)
    if atual is not None:
        dif = comparar_indices(atual, novo)
        print("comparação com o índice atual:", {k: len(v) for k, v in dif.items()})
        for k, v in dif.items():
            if v:
                print(f"  {k}: {v[:12]}{' ...' if len(v) > 12 else ''}")
        if not a.gravar:
            print("nada gravado (use --gravar para substituir o índice atual)")
            return 0
        shutil.copy2(destino, destino.with_name(destino.stem + ".anterior.json"))
    novo.salvar(destino)
    print(f"gravado em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
