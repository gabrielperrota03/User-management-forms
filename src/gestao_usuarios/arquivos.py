"""Gravação tudo-ou-nada (OneDrive/antivírus seguram arquivos no Windows)."""
from __future__ import annotations

import os
import time
from pathlib import Path


def gravar_texto(caminho: Path, texto: str, tentativas: int = 10, espera: float = 0.2) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    for i in range(tentativas):
        try:
            os.replace(tmp, caminho)
            return
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(espera)
