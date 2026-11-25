r"""Gera o índice transação -> single roles (roles_por_transacao.json) da extração `ALL single roles X Transactions.XLSX`.

Rodar UMA vez (a tabela quase não muda); de novo só se alguém refizer a extração. Só biblioteca padrão. O índice vai para
`roles.indice` do config (Insumos - Automação); a planilha e o índice não são versionados.

  python scripts/gerar_indice_roles.py ["C:\Users\L1170904\Sapworkdir\ALL single roles X Transactions.XLSX"]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gestao_usuarios import config  # noqa: E402
from gestao_usuarios.roles import ExtracaoInvalida, IndiceRoles  # noqa: E402

PADRAO = Path(r"C:\Users\L1170904\Sapworkdir\ALL single roles X Transactions.XLSX")


def main() -> int:
    origem = Path(sys.argv[1]) if len(sys.argv) > 1 else PADRAO
    cfg = config.carregar()
    destino = Path(cfg["roles"]["indice"])
    try:
        indice, ressalvas = IndiceRoles.do_xlsx(origem)
    except (OSError, ExtracaoInvalida) as e:
        print(f"nada gerado: {e}")
        return 1
    indice.salvar(destino)
    roles = {r for rs in indice.transacoes.values() for r in rs}
    print(f"{len(indice.transacoes)} transações, {len(roles)} single roles -> {destino}")
    for r in ressalvas:
        print("ressalva:", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
