"""CLI.

  python -m gestao_usuarios rodada  [--executar]          # uma passada na pasta de respostas (pastas.solicitacoes)
  python -m gestao_usuarios processar ARQ.json [--executar] [--relatorios DIR]   # um JSON avulso, sem manifesto
  python -m gestao_usuarios vigiar  [--executar]          # fica olhando a pasta e roda quando chega resposta

Dry-run é o padrão: sem --executar nenhuma request é criada (só a criação de usuário cria request; a modificação só analisa).
Saída: 0 ok, 1 alguma solicitação falhou, 2 SAP/GRC indisponível (login, sessão), 3 configuração inválida, 4 vigia já rodando.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config
from .conexoes import ConexoesReais
from .manifesto import Manifesto
from .processador import Opcoes
from .rotina import Saida, novas_respostas, rodada
from .seguranca import RegrasSeguranca
from .zbr import ListaZbr

log = logging.getLogger("gestao_usuarios")
RAIZ = config.RAIZ


def _logging(verboso: bool) -> None:
    pasta = RAIZ / "logs"
    pasta.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if verboso else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(pasta / f"{datetime.now():%Y-%m-%d}.log", encoding="utf-8")])


def _opcoes(cfg: dict, executar: bool) -> Opcoes:
    r, z = cfg.get("request") or {}, cfg.get("zbr") or {}
    return Opcoes(executar=executar, max_requests=int(r.get("max_por_rodada", 3)),
                  bloquear_com_conflito=bool(r.get("bloquear_com_conflito", True)),
                  zbr_idade_max_dias=float(z.get("idade_max_dias", 8)), zbr_prefixo=z.get("prefixo", "ZBR"),
                  request_grc=bool(r.get("ligada", False)))


def executar_rodada(cfg: dict, arquivos: list[Path], manifesto: Manifesto, executar: bool, relatorios: Path) -> Saida:
    conexoes = ConexoesReais(cfg)
    try:
        return rodada(arquivos, manifesto=manifesto, conexoes=conexoes, regras=RegrasSeguranca.de_config(cfg),
                      opcoes=_opcoes(cfg, executar), pasta_relatorios=relatorios,
                      pasta_trabalho=RAIZ / "logs" / "trabalho" / f"{datetime.now():%Y%m%d_%H%M%S}",
                      lista_zbr=ListaZbr.carregar(Path(cfg["pastas"]["lista_zbr"])), agora=datetime.now())
    finally:
        conexoes.fechar()


def _relatar(saida: Saida) -> None:
    for r in saida.resumos:
        log.info("%s -> %s%s%s", r.arquivo, r.situacao, f" | {r.relatorio}" if r.relatorio else "",
                 f" | ERRO {r.erro}" if r.erro else "")
    if saida.parada:
        log.error("rodada parada: %s", saida.parada)


def cmd_rodada(cfg, args) -> int:
    manifesto = Manifesto(Path(cfg["pastas"]["estado"]))
    arquivos = novas_respostas(Path(cfg["pastas"]["solicitacoes"]), manifesto)
    log.info("%d resposta(s) nova(s)", len(arquivos))
    if not arquivos:
        return 0
    saida = executar_rodada(cfg, arquivos, manifesto, args.executar, Path(cfg["pastas"]["relatorios"]))
    _relatar(saida)
    return saida.codigo


def cmd_processar(cfg, args) -> int:
    """Um JSON avulso (teste/reprocessamento). Manifesto descartável em logs/: não marca nada como tratado."""
    manifesto = Manifesto(RAIZ / "logs" / "trabalho" / f"manifesto_avulso_{datetime.now():%Y%m%d_%H%M%S}.json")
    relatorios = Path(args.relatorios) if args.relatorios else Path(cfg["pastas"]["relatorios"])
    saida = executar_rodada(cfg, [Path(args.arquivo)], manifesto, args.executar, relatorios)
    _relatar(saida)
    return saida.codigo


def _trava(caminho: Path):
    """Instância única da vigia: trava exclusiva num arquivo (liberada quando o processo termina)."""
    import msvcrt

    caminho.parent.mkdir(parents=True, exist_ok=True)
    f = open(caminho, "a+")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    return f


def cmd_vigiar(cfg, args) -> int:
    trava = _trava(RAIZ / "logs" / "vigia.lock")
    if trava is None:
        log.error("já existe uma vigia rodando")
        return 4
    intervalo = float(args.intervalo or (cfg.get("vigia") or {}).get("intervalo_s", 30))
    pasta = Path(cfg["pastas"]["solicitacoes"])
    log.info("vigiando %s a cada %.0f s (%s)", pasta, intervalo, "EXECUTAR" if args.executar else "dry-run")
    espera_extra = 0.0
    while True:
        try:
            manifesto = Manifesto(Path(cfg["pastas"]["estado"]))
            arquivos = novas_respostas(pasta, manifesto)
            if arquivos:
                log.info("%d resposta(s) nova(s)", len(arquivos))
                saida = executar_rodada(cfg, arquivos, manifesto, args.executar, Path(cfg["pastas"]["relatorios"]))
                _relatar(saida)
                espera_extra = 300.0 if saida.parada else 0.0         # SAP/GRC fora: tenta de novo em 5 min
        except KeyboardInterrupt:
            return 0
        except Exception:  # noqa: BLE001 - a vigia não morre por uma rodada ruim
            log.exception("falha na rodada da vigia")
            espera_extra = 60.0
        try:
            time.sleep(intervalo + espera_extra)
        except KeyboardInterrupt:
            return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gestao_usuarios")
    ap.add_argument("-v", "--verboso", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("rodada")
    p.add_argument("--executar", action="store_true")
    p = sub.add_parser("processar")
    p.add_argument("arquivo")
    p.add_argument("--executar", action="store_true")
    p.add_argument("--relatorios")
    p = sub.add_parser("vigiar")
    p.add_argument("--executar", action="store_true")
    p.add_argument("--intervalo", type=float)
    args = ap.parse_args(argv)
    _logging(args.verboso)
    try:
        cfg = config.carregar()
    except Exception as e:  # noqa: BLE001
        log.error("configuração inválida: %s", e)
        return 3
    return {"rodada": cmd_rodada, "processar": cmd_processar, "vigiar": cmd_vigiar}[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
