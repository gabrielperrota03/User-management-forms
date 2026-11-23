"""Prints usados como evidência no relatório (SAP e GRC). Falha de captura nunca derruba a análise: o relatório sai sem a imagem.
Padrão do lock-users: HardCopy do SAP GUI (não depende de foco), reduzida a 1280 px e gravada em PNG."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

LARGURA = 1280


def comprimir(origem: Path, destino: Path, largura: int = LARGURA) -> Path:
    from PIL import Image

    destino.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(origem) as im:
        im = im.convert("RGB")
        if im.width > largura:
            im = im.resize((largura, round(im.height * largura / im.width)), Image.LANCZOS)
        im.save(destino, format="PNG", optimize=True)
    return destino


def capturar_janela_sap(janela, destino: Path) -> Path | None:
    fd, tmp = tempfile.mkstemp(suffix=".bmp")
    os.close(fd)
    try:
        janela.HardCopy(tmp, "BMP")
        return comprimir(Path(tmp), destino)
    except Exception as exc:  # noqa: BLE001
        log.warning("print do SAP falhou (%s): %s", destino.name, exc)
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def capturar_pagina(pagina, destino: Path) -> Path | None:
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        pagina.screenshot(path=tmp, timeout=20000)
        return comprimir(Path(tmp), destino)
    except Exception as exc:  # noqa: BLE001
        log.warning("print do GRC falhou (%s): %s", destino.name, exc)
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
