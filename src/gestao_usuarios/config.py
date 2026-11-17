"""Config em camadas: config/geral.yaml (versionado) + config/geral.local.yaml (por máquina, fora do git).
Variáveis de ambiente no estilo %VAR% (ex.: %OneDriveCommercial%) são expandidas."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]


def _mesclar(base: dict, extra: dict) -> dict:
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mesclar(base[k], v)
        else:
            base[k] = v
    return base


def _expandir(valor):
    if isinstance(valor, dict):
        return {k: _expandir(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_expandir(v) for v in valor]
    if isinstance(valor, str):
        return os.path.expandvars(valor)
    return valor


def carregar(pasta_config: Path | None = None, usar_local: bool = True) -> dict:
    pasta = pasta_config or RAIZ / "config"
    cfg = yaml.safe_load((pasta / "geral.yaml").read_text(encoding="utf-8")) or {}
    local = pasta / "geral.local.yaml"
    if usar_local and local.exists():
        _mesclar(cfg, yaml.safe_load(local.read_text(encoding="utf-8")) or {})
    return _expandir(cfg)
