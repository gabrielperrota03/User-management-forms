r"""Pré-checagem de um IGG candidato para o primeiro teste real da CRIAÇÃO (sem passar pelo Forms).

Um bom candidato é uma pessoa que o **GRC conhece** (nome e e-mail vêm preenchidos e travados no formulário) e que **ainda não tem
usuário no E1P**. Faz exatamente o que o vigia faz em dry-run, e nada além disso:
  1. RFC (somente leitura): o IGG não existe no E1P (BAPI_USER_GET_DETAIL);
  2. ZBR do usuário de referência pela lista semanal;
  3. GRC: abre o formulário de criação (New or Change Account), preenche, confere e **fecha sem Submit**.
O print do formulário (com dados pessoais) fica em logs/validacao/candidatos/ (fora do git).

  python scripts/conferir_candidato.py L1234567 [--referencia L1170904]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from gestao_usuarios import config  # noqa: E402
from gestao_usuarios.conexoes import ConexoesReais  # noqa: E402
from gestao_usuarios.erros import ErroValidacaoGrc, RequestBarrada, SessaoParada, UsuarioSemDadosNoGrc  # noqa: E402
from gestao_usuarios.seguranca import RE_IGG  # noqa: E402
from gestao_usuarios.zbr import ListaZbr  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Confere se um IGG serve para o primeiro teste real da criação (sem Submit).")
    ap.add_argument("igg")
    ap.add_argument("--referencia", default="L1170904", help="usuário de referência (padrão: o analista)")
    a = ap.parse_args()
    igg, ref = a.igg.strip().upper(), a.referencia.strip().upper()
    if not RE_IGG.match(igg) or not RE_IGG.match(ref):
        print(f"IGG inválido (esperado uma letra e 7 números): {igg!r} / {ref!r}")
        return 3
    cfg = config.carregar()
    lista = ListaZbr.carregar(Path(cfg["pastas"]["lista_zbr"]))
    zbrs = (lista.usuarios.get(ref) if lista else None) or ()
    print(f"Candidato {igg}; referência {ref}; ZBR da referência na lista: {', '.join(zbrs) or '(nenhum)'}")
    if len(zbrs) != 1:
        print("NÃO SERVE ainda: a referência precisa ter exatamente um ZBR na lista (escolha outra com --referencia).")
        return 1

    pasta = RAIZ / "logs" / "validacao" / "candidatos" / f"{igg}_{datetime.now():%Y%m%d_%H%M%S}"
    con = ConexoesReais(cfg)
    try:
        con.preparar(pasta)
        usuario = con.sap().usuario(igg)
        if usuario.existe is None:
            print("INCONCLUSIVO: não deu para confirmar o IGG no E1P (leitura incerta). Tente de novo.")
            return 2
        if usuario.existe:
            print(f"NÃO SERVE: {igg} JÁ EXISTE no E1P (a guarda 'só usuário novo' barra a criação). Escolha uma pessoa sem usuário SAP.")
            return 1
        print("E1P (RFC): o IGG não existe no E1P. OK")
        try:
            con.grc_request().criar_usuario(igg, zbrs[0], "Pré-checagem de candidato (ensaio, sem Submit)", submeter=False)
        except UsuarioSemDadosNoGrc as e:
            print(f"NÃO SERVE: o GRC não conhece a pessoa (sem nome/e-mail no formulário). {e}")
            return 1
        except (RequestBarrada, ErroValidacaoGrc) as e:
            print(f"NÃO SERVE: uma trava do formulário do GRC impediu o ensaio: {e}")
            return 1
        print(f"GRC: formulário de criação preenchido e conferido com o ZBR {zbrs[0]}; fechado SEM Submit. OK")
        _, avisos = con.evidencias()
        for x in avisos:
            print("aviso:", x)
        print(f"SERVE: {igg} é um bom candidato para o primeiro teste real da criação. Print em {pasta}")
        return 0
    except SessaoParada as e:
        print(f"INCONCLUSIVO: {e}")
        return 2
    finally:
        con.fechar()


if __name__ == "__main__":
    sys.exit(main())
