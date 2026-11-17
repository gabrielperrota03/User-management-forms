"""Inspeção ao vivo da SUIM (somente leitura) para confirmar o que a gravação não mostra.

Uso:  .venv\\Scripts\\python scripts\\inspecionar_suim.py FB01

Abre uma sessão PRÓPRIA no E1P (as do analista ficam como estão), refaz o caminho gravado sem as conferências e mostra:
texto do nó clicado, programa/transação da tela de seleção, texto do popup depois de executar, colunas e primeiras linhas
da grade. Grava tudo em logs/inspecao/ (JSON + print da janela). Nada é alterado no SAP. Fecha só a sessão que abriu.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from gestao_usuarios import config, sap_gui, suim  # noqa: E402


def main() -> int:
    transacao = (sys.argv[1] if len(sys.argv) > 1 else "FB01").upper()
    cfg = config.carregar()
    c = suim.ConfigSuim.de_config(cfg)
    pasta = RAIZ / "logs" / "inspecao"
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = f"{datetime.now():%Y%m%d_%H%M%S}"
    achado: dict = {"transacao": transacao}
    with sap_gui.SessaoPropria("E1P", cfg["sap"].get("conexao_e1p")) as s:
        achado["sistema"] = f"{s.Info.SystemName}/{s.Info.Client}"
        achado["titulo_selecao"] = suim.abrir_relatorio(s, c, conferir=False)
        achado["programa"] = str(s.Info.Program)
        achado["transacao_sap"] = str(s.Info.Transaction)
        popup, grade = suim.executar_busca(s, c, transacao, conferir=False)
        achado["popup"] = popup
        achado["titulo_resultado"] = sap_gui.titulo(s)
        colunas, linhas = sap_gui.ler_grade(grade)
        achado["colunas"] = colunas
        achado["total_linhas"] = len(linhas)
        achado["primeiras_linhas"] = linhas[:30]
        try:
            s.findById("wnd[0]").HardCopy(str(pasta / f"suim_{transacao}_{carimbo}.bmp"), "BMP")
        except Exception as e:  # noqa: BLE001
            achado["print"] = f"falhou: {e}"
    destino = pasta / f"suim_{transacao}_{carimbo}.json"
    destino.write_text(json.dumps(achado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(achado, ensure_ascii=False, indent=2))
    print(f"\nGravado em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
