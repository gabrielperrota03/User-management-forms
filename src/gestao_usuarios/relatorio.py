"""Relatório de uma solicitação: pasta com o HTML (prints embutidos no corpo) e os PNG originais.

Pasta: <relatorios>/AAAA-MM/AAAAMMDD_HHMMSS_<id da resposta>/. O HTML se chama AAAAMMDD_HHMMSS_<assunto>.html: o fluxo do Power
Automate (copiado do lock-users) usa o nome do arquivo sem os 16 primeiros caracteres como assunto do e-mail. É gravado POR
ÚLTIMO (via .tmp + troca) porque é ele que dispara o fluxo. Os prints vão embutidos em base64 no corpo (como no lock-users),
com um teto de quantidade e de tamanho; os que passarem do teto só ficam na pasta. Todo texto que veio do Forms é escapado.
"""
from __future__ import annotations

import base64
import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path

from .analise import NIVEIS
from .arquivos import gravar_texto
from .decisao import Acao, AcaoRequest
from .processador import Resultado
from .resposta import Tipo

PREFIXO_ASSUNTO = "[gestao-usuarios]"
MAX_PRINTS_EMBUTIDOS = 16
MAX_BYTES_EMBUTIDOS = 4_000_000          # PNG somados (o base64 cresce ~33%); acima disso só ficam na pasta
CORES = {"Critical": "#b00020", "High": "#d35400", "Medium": "#b7950b", "Low": "#2e86c1"}


COR_SITUACAO = {"OK": "#1e8449", "CONFLITO": "#b00020", "AVISO": "#b7950b", "RECUSADA": "#555",
                "PARA CRIAR": "#2e86c1", "REQUEST CRIADA": "#1e8449"}
_FALHAS_DA_REQUEST = (AcaoRequest.FALHOU_SUBMIT, AcaoRequest.BARRADA_FORMULARIO, AcaoRequest.BARRADA_USUARIO_EXISTE,
                      AcaoRequest.BARRADA_LEITURA_INCERTA)


def situacao(res: Resultado) -> str:
    """Modificação: RECUSADA, AVISO (um humano decide), CONFLITO (algum risco) ou OK (sem risco).
    Criação: RECUSADA, AVISO, CONFLITO, PARA CRIAR (tudo conferido; a request é à mão enquanto estiver desligada) ou REQUEST CRIADA."""
    if res.recusada:
        return "RECUSADA"
    if res.acao is not Acao.ANALISAR:
        return "AVISO"
    if res.solicitacao.tipo is Tipo.CRIACAO:
        if res.acao_request in _FALHAS_DA_REQUEST:
            return "AVISO"
        if res.comparativo is not None:
            if not res.comparativo.completo:
                return "AVISO"
            if res.comparativo.conflito:
                return "CONFLITO"
        return "REQUEST CRIADA" if res.acao_request is AcaoRequest.CRIAR else "PARA CRIAR"
    if res.comparativo is None or not res.comparativo.completo:
        return "AVISO"
    if res.comparativo.conflito:
        return "CONFLITO"
    if res.comparativo.sem_role:
        return "AVISO"
    return "OK"


def _zbr_texto(res: Resultado) -> str:
    return res.zbr or (", ".join(res.zbrs) if res.zbrs else "")


def assunto(res: Resultado) -> str:
    s = res.solicitacao
    if s.tipo is Tipo.CRIACAO:
        detalhe = f"ZBR {_zbr_texto(res)}" if _zbr_texto(res) else f"ref. {s.usuario_referencia or '?'}"
        return f"{PREFIXO_ASSUNTO} Criação {s.igg} - {situacao(res)} ({detalhe})"
    return f"{PREFIXO_ASSUNTO} Modificação {s.igg} - {situacao(res)} ({', '.join(s.transacoes) or 'sem transações'})"


def _texto_request(res: Resultado) -> str:
    return {
        AcaoRequest.NAO_SE_APLICA: "",
        AcaoRequest.DESLIGADA: "A request <b>não foi aberta</b> no GRC (desligado por enquanto: este e-mail é só o aviso). "
                               "Abrir à mão com o ZBR indicado acima.",
        AcaoRequest.CRIAR: f"Request de criação criada: <b>{escape(res.request or '')}</b>",
        AcaoRequest.SIMULAR: "Dry-run: a request de criação <b>seria criada</b> (rode com --executar).",
        AcaoRequest.BARRADA_USUARIO_EXISTE: "Request NÃO criada: o usuário passou a existir no E1P.",
        AcaoRequest.BARRADA_LEITURA_INCERTA: "Request NÃO criada: não deu para confirmar o usuário no E1P.",
        AcaoRequest.BARRADA_CONFLITO: "Request NÃO criada: a análise encontrou conflito de risco.",
        AcaoRequest.BARRADA_ANALISE_INCOMPLETA: "Request NÃO criada: a análise ficou incompleta.",
        AcaoRequest.BARRADA_DISJUNTOR: "Request NÃO criada: limite de requests da rodada atingido (próxima rodada).",
        AcaoRequest.BARRADA_FORMULARIO: "Request NÃO criada: uma trava do formulário do GRC a impediu (ver os avisos).",
        AcaoRequest.FALHOU_SUBMIT: "<b>ATENÇÃO:</b> o Submit no GRC não foi confirmado. A request PODE ter sido criada: "
                                   "conferir no Request Status antes de repetir (ver os avisos).",
    }[res.acao_request]


# ------------------------------------------------------------------ blocos comuns
def _abrir(res: Resultado, titulo: str) -> str:
    sit = situacao(res)
    cor = COR_SITUACAO[sit]
    return f"""<html><head><meta charset="utf-8"><title>{escape(assunto(res))}</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;font-size:13px;color:#222}} table{{border-collapse:collapse;margin:6px 0 14px}}
td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top}} th{{background:#f2f2f2}}
.sit{{display:inline-block;padding:3px 10px;color:#fff;background:{cor};border-radius:3px;font-weight:bold}}
</style></head><body>
<h2>{titulo} <span class="sit">{sit}</span></h2>"""


def _tabela(linhas: list[tuple[str, str]]) -> str:
    """Linhas (rótulo, HTML já escapado)."""
    return "<table>" + "".join(f"<tr><th>{r}</th><td>{v}</td></tr>" for r, v in linhas) + "</table>"


def _dados_do_pedido(res: Resultado) -> list[tuple[str, str]]:
    s = res.solicitacao
    return [("Justificativa", escape(s.justificativa)),
            ("Solicitante", f"{escape(s.solicitante_nome)} &lt;{escape(s.solicitante_email)}&gt;"),
            ("Enviado em", escape(s.enviado_em or "")),
            ("Resposta do Forms", escape(s.id_resposta))]


def _bloco_recusa(res: Resultado) -> str:
    return "<h3>Recusada pelas regras de segurança</h3><ul>" + "".join(f"<li>{escape(m)}</li>" for m in res.recusa) + "</ul>"


def _bloco_avisos(res: Resultado) -> str:
    return "<h3>Avisos</h3><ul>" + "".join(f"<li>{escape(a)}</li>" for a in res.avisos) + "</ul>" if res.avisos else ""


def _bloco_analise(res: Resultado) -> str:
    if res.comparativo is None:
        return ""
    p = [f"<h3>Análise de risco (GRC, simulação em {escape(res.alvo_simulacao or '')}, Rule Set EP - SOD 2019, "
         "só riscos trazidos pela role)</h3>"]
    for t, lista in res.comparativo.por_transacao.items():
        p.append(f"<h4>{escape(t)}</h4>")
        if not lista:
            p.append("<p>Nenhuma single role dá acesso a esta transação.</p>")
            continue
        rec = res.comparativo.recomendada(t)
        p.append("<table><tr><th>Single role</th><th>Críticos</th><th>Detalhe</th></tr>")
        for r in lista:
            c = r.contagem()
            marca = " ★ menor risco" if len(lista) > 1 and rec is not None and r is rec else ""
            if r.erro:
                detalhe = f"<i>simulação falhou: {escape(r.erro)}</i>"
            elif r.riscos:
                detalhe = "<br>".join(f"<b style='color:{CORES.get(x.nivel, '#222')}'>{escape(x.id)}</b> "
                                      f"({escape(x.nivel)}) {escape(x.descricao)}" for x in r.riscos)
            else:
                detalhe = "sem risco"
            p.append(f"<tr><td>{escape(r.role)}{marca}</td><td>{'—' if r.erro else c['Critical']}</td><td>{detalhe}</td></tr>")
        p.append("</table>")
    return "".join(p)


def _bloco_evidencias(prints: list[tuple[str, str | None]]) -> str:
    if not prints:
        return ""
    p = ["<h3>Evidências</h3>"]
    for nome, uri in prints:
        if uri:
            p.append(f"<p><b>{escape(nome)}</b><br><img src=\"{uri}\" style=\"width:100%;max-width:1700px;border:1px solid #ccc\"></p>")
        else:
            p.append(f"<p><b>{escape(nome)}</b>: não embutida (limite do e-mail); está na pasta do relatório.</p>")
    return "".join(p)


def _rodape(gerado_em: datetime) -> str:
    return f"<p style='color:#888'>Gerado em {gerado_em:%d/%m/%Y %H:%M} pela automação User-management-forms.</p></body></html>"


# ------------------------------------------------------------------ modificação
def _html_modificacao(res: Resultado, prints: list[tuple[str, str | None]], gerado_em: datetime) -> str:
    s = res.solicitacao
    p = [_abrir(res, "Solicitação de acesso SAP (E1P)"),
         _tabela([("Tipo", "Modificação de acesso"), ("IGG", escape(s.igg)),
                  ("Transações", escape(", ".join(s.transacoes)) or "(nenhuma)"), *_dados_do_pedido(res)])]
    if res.recusa:
        p.append(_bloco_recusa(res))
    elif res.acao is not Acao.ANALISAR:
        p.append(f"<h3>Não analisada</h3><p>{escape(res.motivo)}</p>")
    p += [_bloco_avisos(res), _bloco_analise(res), _bloco_evidencias(prints), _rodape(gerado_em)]
    return "\n".join(x for x in p if x)


# ------------------------------------------------------------------ criação
def _estado(rotulo: str, cor: str, detalhe: str = "") -> str:
    return f"<b style='color:{cor}'>{rotulo}</b>" + (f" {escape(detalhe)}" if detalhe else "")


def _conferencias_da_criacao(res: Resultado) -> list[tuple[str, str]]:
    """O que foi conferido no E1P para a criação: o usuário é novo? a referência existe? tem um ZBR só?"""
    ok, ruim, incerto, nada = "#1e8449", "#b00020", "#b7950b", "#888"
    u, ref, zbrs = res.usuario, res.referencia, res.zbrs
    if u is None:
        novo = _estado("não verificado", nada)
    elif u.existe is None:
        novo = _estado("NÃO CONFIRMADO", incerto, "(leitura incerta no E1P)")
    elif u.existe:
        novo = _estado("JÁ EXISTE", ruim, "no E1P: verificar se o pedido é uma modificação")
    else:
        novo = _estado("OK", ok, "não existe no E1P")
    if ref is None:
        existe_ref = _estado("não verificado", nada)
    elif ref.existe is None:
        existe_ref = _estado("NÃO CONFIRMADO", incerto, "(leitura incerta no E1P)")
    elif ref.existe:
        existe_ref = _estado("OK", ok, "existe no E1P")
    else:
        existe_ref = _estado("NÃO EXISTE", ruim, "no E1P")
    if zbrs is None:
        zbr = _estado("não verificado", nada)
    elif len(zbrs) == 1:
        zbr = _estado("OK", ok, zbrs[0])
    elif not zbrs:
        zbr = _estado("NENHUM", ruim, "ZBR encontrado para a referência")
    else:
        zbr = _estado("VÁRIOS", ruim, ", ".join(zbrs) + ": escolher à mão")
    return [("O novo usuário ainda não existe no E1P", novo), ("O usuário de referência existe no E1P", existe_ref),
            ("ZBR do usuário de referência", zbr)]


def _html_criacao(res: Resultado, prints: list[tuple[str, str | None]], gerado_em: datetime) -> str:
    s = res.solicitacao
    zbr = _zbr_texto(res)
    p = [_abrir(res, "Pedido de criação de usuário SAP (E1P)"),
         "<h3>Pedido</h3>" + _tabela([("Novo usuário (IGG)", escape(s.igg)),
                                      ("Usuário de referência", escape(s.usuario_referencia or "")),
                                      ("Perfil a atribuir (ZBR)", escape(zbr) if zbr else "—"), *_dados_do_pedido(res)])]
    if res.recusa:
        p.append(_bloco_recusa(res))
    else:
        p.append("<h3>Conferências no E1P</h3>" + _tabela(_conferencias_da_criacao(res)))
        if res.acao is not Acao.ANALISAR:
            p.append(f"<h3>Resultado</h3><p>{escape(res.motivo)}</p>")
        else:
            conferido = (f"Tudo conferido: o usuário {escape(s.igg)} pode ser criado com o ZBR {escape(zbr)} "
                         f"(perfil de {escape(s.usuario_referencia or '')}). ")
            p.append(f"<h3>Resultado</h3><p>{conferido}{_texto_request(res)}</p>")
    p += [_bloco_avisos(res), _bloco_analise(res), _bloco_evidencias(prints), _rodape(gerado_em)]
    return "\n".join(x for x in p if x)


def montar_html(res: Resultado, prints: list[tuple[str, str | None]], gerado_em: datetime) -> str:
    """`prints` = [(nome do arquivo, data URI do PNG ou None se passou do teto)]. Criação e modificação têm estruturas próprias."""
    if res.solicitacao.tipo is Tipo.CRIACAO:
        return _html_criacao(res, prints, gerado_em)
    return _html_modificacao(res, prints, gerado_em)


def _nome_pasta(res: Resultado, gerado_em: datetime) -> str:
    ident = re.sub(r"[^A-Za-z0-9_-]", "_", res.solicitacao.id_resposta)[:40]
    return f"{gerado_em:%Y%m%d_%H%M%S}_{ident}"


def nome_do_html(res: Resultado, gerado_em: datetime) -> str:
    """AAAAMMDD_HHMMSS_<assunto>.html: o prefixo tem 16 caracteres (o fluxo os corta) e o assunto perde o que o SharePoint não
    aceita em nome de arquivo (as transações podem ter '/')."""
    limpo = re.sub(r'[\/:*?"<>|#%~&{}]', "_", assunto(res)).strip(" .")[:150]
    return f"{gerado_em:%Y%m%d_%H%M%S}_{limpo}.html"


def _embutir(origens: list[Path]) -> list[tuple[str, str | None]]:
    """[(nome, data URI)] dos PNG na ordem, até o teto de quantidade e de bytes; o resto vai com uri None."""
    saida, total = [], 0
    for i, origem in enumerate(origens, 1):
        nome = f"{i:02d}_{Path(origem).name}"
        dados = Path(origem).read_bytes()
        if len(saida) < MAX_PRINTS_EMBUTIDOS and total + len(dados) <= MAX_BYTES_EMBUTIDOS:
            total += len(dados)
            saida.append((nome, "data:image/png;base64," + base64.b64encode(dados).decode("ascii")))
        else:
            saida.append((nome, None))
    return saida


def gravar(res: Resultado, prints: list[Path], raiz: Path, gerado_em: datetime) -> Path:
    """Grava a pasta do relatório e devolve o caminho do HTML (gravado por último)."""
    pasta = raiz / f"{gerado_em:%Y-%m}" / _nome_pasta(res, gerado_em)
    pasta.mkdir(parents=True, exist_ok=True)
    existentes = [Path(o) for o in prints if Path(o).exists()]
    for i, origem in enumerate(existentes, 1):
        shutil.copyfile(origem, pasta / f"{i:02d}_{origem.name}")
    destino = pasta / nome_do_html(res, gerado_em)
    gravar_texto(destino, montar_html(res, _embutir(existentes), gerado_em))
    return destino
