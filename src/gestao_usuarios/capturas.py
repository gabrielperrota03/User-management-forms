"""Prints usados como evidência no relatório (SAP e GRC). Falha de captura nunca derruba a análise: o relatório sai sem a imagem.
Padrão do lock-users: HardCopy do SAP GUI (não depende de foco), reduzida a 1280 px e gravada em PNG."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

LARGURA = 1280
LARGURA_GRC = 1700                  # prints do GRC: recortados no conteúdo e quase sem redução, para o texto ficar legível


def comprimir(origem: Path, destino: Path, largura: int = LARGURA, recortar: bool = False) -> Path:
    from PIL import Image

    destino.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(origem) as im:
        im = im.convert("RGB")
        if recortar:
            im = recortar_conteudo(im)
        if im.width > largura:
            im = im.resize((largura, round(im.height * largura / im.width)), Image.LANCZOS)
        im.save(destino, format="PNG", optimize=True)
    return destino


def recortar_conteudo(im, margem: int = 14):
    """Tira o fundo vazio em volta (a janela do GRC é enorme e a tela ocupa só o canto): ganha zoom sem perder nada."""
    from PIL import Image, ImageChops

    fundo = im.getpixel((im.width - 1, im.height - 1))
    dif = ImageChops.difference(im, Image.new("RGB", im.size, fundo)).convert("L").point(lambda v: 255 if v > 12 else 0)
    caixa = dif.getbbox()
    if not caixa:
        return im
    x0, y0, x1, y1 = caixa
    return im.crop((max(x0 - margem, 0), max(y0 - margem, 0), min(x1 + margem, im.width), min(y1 + margem, im.height)))


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
        return comprimir(Path(tmp), destino, largura=LARGURA_GRC, recortar=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("print do GRC falhou (%s): %s", destino.name, exc)
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
