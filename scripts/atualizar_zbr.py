"""Atualização semanal da lista de ZBR (O97 › User x Business Roles Report, BR-TEP, E1PCLNT010). Somente leitura no SAP.

Uso:  .venv\\Scripts\\python scripts\\atualizar_zbr.py                 # grava em pastas.lista_zbr do config
      .venv\\Scripts\\python scripts\\atualizar_zbr.py --destino X.json  # grava em outro arquivo (teste)

Abre uma sessão PRÓPRIA no O97 (as do analista ficam como estão) e fecha só ela. A lista nova só substitui a atual se for
plausível (não encolheu mais de 20%). Saída: 0 gravou, 1 recusou (lista atual mantida), 2 SAP indisponível.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from gestao_usuarios import config  # noqa: E402
from gestao_usuarios.erros import SessaoParada  # noqa: E402
from gestao_usuarios.sap_o97 import ConfigO97, FonteZbrO97, atualizar_lista  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", type=Path)
    args = ap.parse_args()
    cfg = config.carregar()
    destino = args.destino or Path(cfg["pastas"]["lista_zbr"])
    try:
        extraidos = FonteZbrO97(ConfigO97.de_config(cfg)).extrair_todos()
    except SessaoParada as e:
        print(f"SAP indisponível: {e}")
        return 2
    gravou, msg = atualizar_lista(extraidos, destino, datetime.now())
    print(("Gravado em " + str(destino) + ": " if gravou else "Recusado: ") + msg)
    return 0 if gravou else 1


if __name__ == "__main__":
    sys.exit(main())
