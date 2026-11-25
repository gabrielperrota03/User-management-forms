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


def situacao(res: Resultado) -> str:
    """RECUSADA (guardas), AVISO (um humano decide), CONFLITO (algum risco), OK (sem risco)."""
    if res.recusada:
        return "RECUSADA"
    if res.acao is not Acao.ANALISAR:
        return "AVISO"
    if res.sem_analise:                                 # criação sem transações: nada foi analisado
        return "AVISO" if res.acao_request in (AcaoRequest.FALHOU_SUBMIT, AcaoRequest.BARRADA_FORMULARIO) else "SEM ANÁLISE"
    if res.comparativo is None or not res.comparativo.completo:
        return "AVISO"
    if res.acao_request in (AcaoRequest.FALHOU_SUBMIT, AcaoRequest.BARRADA_FORMULARIO):
        return "AVISO"
    if res.comparativo.conflito:
        return "CONFLITO"
    if res.comparativo.sem_role:
        return "AVISO"
    return "OK"


def assunto(res: Resultado) -> str:
    s = res.solicitacao
    tipo = "Criação" if s.tipo is Tipo.CRIACAO else "Modificação"
    return f"{PREFIXO_ASSUNTO} {tipo} {s.igg} - {situacao(res)} ({', '.join(s.transacoes) or 'sem transações'})"


def _texto_request(res: Resultado) -> str:
    return {
        AcaoRequest.NAO_SE_APLICA: "",
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


def montar_html(res: Resultado, prints: list[tuple[str, str | None]], gerado_em: datetime) -> str:
    """`prints` = [(nome do arquivo, data URI do PNG ou None se passou do teto)]."""
    s = res.solicitacao
    sit = situacao(res)
    cor = {"OK": "#1e8449", "CONFLITO": "#b00020", "AVISO": "#b7950b", "RECUSADA": "#555", "SEM ANÁLISE": "#2e86c1"}[sit]
    p = [f"""<html><head><meta charset="utf-8"><title>{escape(assunto(res))}</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;font-size:13px;color:#222}} table{{border-collapse:collapse;margin:6px 0 14px}}
td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top}} th{{background:#f2f2f2}}
.sit{{display:inline-block;padding:3px 10px;color:#fff;background:{cor};border-radius:3px;font-weight:bold}}
</style></head><body>
<h2>Solicitação de acesso SAP (E1P) <span class="sit">{sit}</span></h2>
<table>
<tr><th>Tipo</th><td>{"Criação de usuário" if s.tipo is Tipo.CRIACAO else "Modificação de acesso"}</td></tr>
<tr><th>IGG</th><td>{escape(s.igg)}</td></tr>"""]
    if s.tipo is Tipo.CRIACAO:
        p.append(f"<tr><th>Usuário de referência</th><td>{escape(s.usuario_referencia or '')}"
                 f"{' (ZBR ' + escape(res.zbr) + ')' if res.zbr else ''}</td></tr>")
    p.append(f"""<tr><th>Transações</th><td>{escape(', '.join(s.transacoes)) or '(nenhuma)'}</td></tr>
<tr><th>Justificativa</th><td>{escape(s.justificativa)}</td></tr>
<tr><th>Solicitante</th><td>{escape(s.solicitante_nome)} &lt;{escape(s.solicitante_email)}&gt;</td></tr>
<tr><th>Enviado em</th><td>{escape(s.enviado_em or '')}</td></tr>
<tr><th>Resposta do Forms</th><td>{escape(s.id_resposta)}</td></tr>
</table>""")
    if res.recusa:
        p.append("<h3>Recusada pelas regras de segurança</h3><ul>" + "".join(f"<li>{escape(m)}</li>" for m in res.recusa) + "</ul>")
    elif res.acao is not Acao.ANALISAR:
        p.append(f"<h3>Não analisada</h3><p>{escape(res.motivo)}</p>")
    if res.avisos:
        p.append("<h3>Avisos</h3><ul>" + "".join(f"<li>{escape(a)}</li>" for a in res.avisos) + "</ul>")
    if res.sem_analise:
        p.append("<h3>Análise de risco</h3><p>Nenhuma transação foi pedida (a criação usa o perfil do usuário de referência): "
                 "<b>não houve análise de risco</b>.</p>")
    if res.comparativo is not None:
        p.append(f"<h3>Análise de risco (GRC, simulação em {escape(res.alvo_simulacao or '')}, Rule Set EP - SOD 2019, "
                 "só riscos trazidos pela role)</h3>")
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
    req = _texto_request(res)
    if req:
        p.append(f"<h3>Request no GRC</h3><p>{req}</p>")
    if prints:
        p.append("<h3>Evidências</h3>")
        for nome, uri in prints:
            if uri:
                p.append(f"<p><b>{escape(nome)}</b><br><img src=\"{uri}\" style=\"width:100%;max-width:1700px;border:1px solid #ccc\"></p>")
            else:
                p.append(f"<p><b>{escape(nome)}</b>: não embutida (limite do e-mail); está na pasta do relatório.</p>")
    p.append(f"<p style='color:#888'>Gerado em {gerado_em:%d/%m/%Y %H:%M} pela automação User-management-forms.</p>"
             "</body></html>")
    return "\n".join(p)


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
