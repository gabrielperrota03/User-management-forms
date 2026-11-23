"""Rodada e relatório com SAP/GRC simulados."""
import base64
import json
from datetime import datetime
from pathlib import Path

from gestao_usuarios import relatorio
from gestao_usuarios.analise import Risco
from gestao_usuarios.decisao import UsuarioSap
from gestao_usuarios.erros import SessaoParada
from gestao_usuarios.manifesto import Fase, Manifesto
from gestao_usuarios.processador import Opcoes
from gestao_usuarios.rotina import novas_respostas, rodada
from gestao_usuarios.seguranca import RegrasSeguranca

from .conftest import GrcRequestFalso, GrcRiscoFalso, SapFalso, resposta

AGORA = datetime(2026, 11, 23, 10, 0)
SF028 = Risco("SF028_EP", "Adjust the subsidiary balance <script>", "Medium")


class ConexoesFalsas:
    def __init__(self, sap=None, risco=None, parar_em=None):
        self._sap = sap or SapFalso({"L1234567": UsuarioSap(True, False)},
                                    {"FB01": ("Y-BRF-FB01-POST_DOCUMENT", "Y-BRA-DEPRECIATION_PROCESSING")})
        self._risco = risco or GrcRiscoFalso({"Y-BRF-FB01-POST_DOCUMENT": (SF028,)})
        self.parar_em = parar_em
        self.abertas = set()
        self.pastas = []
        self.prints = []

    def sap(self):
        self.abertas.add("sap")
        return self._sap

    def grc_risco(self):
        self.abertas.add("grc")
        if self.parar_em == "grc":
            raise SessaoParada("GRC expirou")
        return self._risco

    def grc_request(self):
        return GrcRequestFalso()

    def fonte_zbr(self):
        return None

    def preparar(self, pasta):
        self.pastas.append(pasta)
        self.prints = []

    def evidencias(self):
        return self.prints, ["SUIM (FB01): 523 roles não exibidas"]

    def fechar(self):
        pass


def escrever(pasta: Path, nome: str, **campos) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / nome
    arq.write_text(json.dumps(resposta(transacoes="FB01", **campos)), encoding="utf-8")
    return arq


def rodar(tmp_path, arquivos, conexoes, manifesto=None):
    manifesto = manifesto or Manifesto(tmp_path / "estado.json")
    saida = rodada(arquivos, manifesto=manifesto, conexoes=conexoes, regras=RegrasSeguranca(), opcoes=Opcoes(),
                   pasta_relatorios=tmp_path / "rel", pasta_trabalho=tmp_path / "trab", lista_zbr=None, agora=AGORA)
    return saida, manifesto


def test_modificacao_ponta_a_ponta(tmp_path):
    arq = escrever(tmp_path / "sol" / "11_26", "20261123_100000_42.json")
    con = ConexoesFalsas()
    png = tmp_path / "suim_FB01.png"
    png.write_bytes(b"PNG-teste")
    con.prints = [png]
    con.evidencias = lambda: ([png], ["SUIM (FB01): 523 roles não exibidas"])
    saida, man = rodar(tmp_path, [arq], con)
    assert saida.codigo == 0 and saida.resumos[0].situacao == "CONFLITO"
    html = saida.resumos[0].relatorio.read_text(encoding="utf-8")
    pasta = saida.resumos[0].relatorio.parent
    assert "SF028_EP" in html and "Y-BRF-FB01-POST_DOCUMENT" in html and "★ menor risco" in html
    assert html.count("★ menor risco") == 1
    assert "&lt;script&gt;" in html and "<script>" not in html, "texto escapado"
    assert "523 roles" in html
    assert (pasta / "01_suim_FB01.png").exists()
    assert saida.resumos[0].relatorio.name.endswith("_[gestao-usuarios] Modificação L1234567 - CONFLITO (FB01).html")
    assert "<title>[gestao-usuarios] Modificação L1234567 - CONFLITO (FB01)</title>" in html
    assert 'src="data:image/png;base64,' + base64.b64encode(b"PNG-teste").decode() + '"' in html, "print embutido no corpo"
    e = Manifesto(tmp_path / "estado.json").entradas["42"]
    assert e.fase is Fase.CONCLUIDA and e.conflito is True and e.arquivo == arq.name


def test_unica_candidata_nao_leva_estrela(tmp_path):
    arq = escrever(tmp_path / "sol", "a.json")
    sap = SapFalso({"L1234567": UsuarioSap(True, False)}, {"FB01": ("Y-BRF-FB01-POST_DOCUMENT",)})
    saida, _ = rodar(tmp_path, [arq], ConexoesFalsas(sap=sap))
    assert "★" not in saida.resumos[0].relatorio.read_text(encoding="utf-8")


class ConexoesComRequest(ConexoesFalsas):
    def __init__(self, request, **kw):
        super().__init__(**kw)
        self.request = request

    def grc_request(self):
        self.abertas.add("request")
        return self.request


def _criacao(tmp_path, executar, request, **campos):
    from gestao_usuarios.zbr import ListaZbr
    arq = escrever(tmp_path / "sol", "a.json", tipo="Criação de usuário", usuario_referencia="L7654321", **campos)
    sap = SapFalso({"L7654321": UsuarioSap(True)}, {"FB01": ("Y-BRF-FB01-POST_DOCUMENT",)})
    con = ConexoesComRequest(request, sap=sap, risco=GrcRiscoFalso())
    manifesto = Manifesto(tmp_path / "estado.json")
    saida = rodada([arq], manifesto=manifesto, conexoes=con, regras=RegrasSeguranca(), opcoes=Opcoes(executar=executar),
                   pasta_relatorios=tmp_path / "rel", pasta_trabalho=tmp_path / "trab",
                   lista_zbr=ListaZbr(AGORA, {"L7654321": ("ZBRCOORD",)}), agora=AGORA)
    return saida, manifesto, con


def test_criacao_executar_passa_pela_rodada_e_grava_o_numero(tmp_path):
    request = GrcRequestFalso()
    saida, man, con = _criacao(tmp_path, True, request, igg="L1234567")
    assert request.criadas == [("L1234567", "ZBRCOORD", "Criação de usuário L1234567 (ZBR ZBRCOORD) - Forms 42")]
    assert saida.resumos[0].situacao == "OK" and man.entradas["42"].request == "700001" and man.entradas["42"].fase is Fase.CONCLUIDA
    assert "700001" in saida.resumos[0].relatorio.read_text(encoding="utf-8")


def test_criacao_dry_run_ensaia_sem_submeter_e_volta_na_proxima(tmp_path):
    request = GrcRequestFalso()
    saida, man, _ = _criacao(tmp_path, False, request, igg="L1234567")
    assert request.criadas == [] and len(request.ensaios) == 1
    assert man.entradas["42"].fase is Fase.ANALISADA and man.entradas["42"].request is None
    assert "ensaio da request" in saida.resumos[0].relatorio.read_text(encoding="utf-8")


def test_criacao_barrada_pelo_formulario_vira_aviso_no_relatorio(tmp_path):
    from gestao_usuarios.erros import UsuarioSemDadosNoGrc
    request = GrcRequestFalso(UsuarioSemDadosNoGrc("o GRC não preencheu First Name, Last Name, Email para L1234567"))
    saida, man, _ = _criacao(tmp_path, True, request, igg="L1234567")
    assert saida.resumos[0].situacao == "AVISO" and man.entradas["42"].fase is Fase.CONCLUIDA
    assert request.criadas == [] and "First Name" in saida.resumos[0].relatorio.read_text(encoding="utf-8")


def test_sem_risco_e_ok(tmp_path):
    arq = escrever(tmp_path / "sol", "a.json")
    saida, _ = rodar(tmp_path, [arq], ConexoesFalsas(risco=GrcRiscoFalso()))
    assert saida.resumos[0].situacao == "OK"


def test_resposta_ja_tratada_e_arquivo_novo_nao_repetem(tmp_path):
    arq = escrever(tmp_path / "sol", "a.json")
    con = ConexoesFalsas()
    _, man = rodar(tmp_path, [arq], con)
    assert novas_respostas(tmp_path / "sol", man) == []
    copia = escrever(tmp_path / "sol", "b.json")                          # mesmo id_resposta em outro arquivo
    saida, _ = rodar(tmp_path, [copia], ConexoesFalsas(), man)
    assert saida.resumos == []


def test_recusada_nao_abre_sap_nem_grc(tmp_path):
    arq = escrever(tmp_path / "sol", "a.json", igg="XYZ")
    con = ConexoesFalsas()
    saida, man = rodar(tmp_path, [arq], con)
    assert saida.resumos[0].situacao == "RECUSADA" and con.abertas == set()
    assert man.entradas["42"].fase is Fase.RECUSADA


def test_json_invalido(tmp_path):
    (tmp_path / "sol").mkdir()
    arq = tmp_path / "sol" / "ruim.json"
    arq.write_text("{", encoding="utf-8")
    saida, man = rodar(tmp_path, [arq], ConexoesFalsas())
    assert saida.codigo == 1 and man.entradas["ruim.json"].fase is Fase.RECUSADA


def test_sessao_parada_deixa_pendente(tmp_path):
    arq = escrever(tmp_path / "sol", "a.json")
    saida, man = rodar(tmp_path, [arq], ConexoesFalsas(parar_em="grc"))
    assert saida.codigo == 2 and "42" not in man.entradas
    assert novas_respostas(tmp_path / "sol", man) == [arq]


def test_falha_numa_solicitacao_vira_aviso_e_segue(tmp_path):
    class SapQuebrado(SapFalso):
        def singles_por_transacao(self, t):
            raise RuntimeError("tela inesperada na SUIM")
    a = escrever(tmp_path / "sol", "a.json")
    b = escrever(tmp_path / "sol", "b.json", id_resposta="43")
    con = ConexoesFalsas(sap=SapQuebrado({"L1234567": UsuarioSap(True, False)}))
    saida, man = rodar(tmp_path, [a, b], con)
    assert [r.situacao for r in saida.resumos] == ["AVISO", "AVISO"] and saida.codigo == 1
    assert man.entradas["42"].fase is Fase.AVISO
    assert "falha na análise" in saida.resumos[0].relatorio.read_text(encoding="utf-8")


def test_html_gravado_por_ultimo(tmp_path, monkeypatch):
    ordem = []
    real = relatorio.gravar_texto
    monkeypatch.setattr(relatorio, "gravar_texto", lambda c, t: (ordem.append(c.name), real(c, t)))
    arq = escrever(tmp_path / "sol", "a.json")
    rodar(tmp_path, [arq], ConexoesFalsas())
    assert len(ordem) == 1 and ordem[0].endswith(".html"), "só o HTML é gravado por texto, e por último"


def test_nome_do_html_para_o_fluxo(tmp_path):
    """O fluxo corta os 16 primeiros caracteres (AAAAMMDD_HHMMSS_) e o '.html' (5): sobra o assunto."""
    arq = escrever(tmp_path / "sol", "a.json")
    saida, _ = rodar(tmp_path, [arq], ConexoesFalsas())
    nome = saida.resumos[0].relatorio.name
    assert nome[:16] == "20261123_" + nome[9:16] and nome[8] == "_" and nome[15] == "_"
    assert nome[16:-5] == "[gestao-usuarios] Modificação L1234567 - CONFLITO (FB01)"


def test_caracteres_invalidos_no_nome_do_arquivo():
    from datetime import datetime as dt
    from gestao_usuarios.processador import Resultado
    from .conftest import solicitacao
    res = Resultado(solicitacao(transacoes="/SCWM/MON, FB01"), motivo="x")
    nome = relatorio.nome_do_html(res, dt(2026, 11, 23, 10, 0, 0))
    assert nome.startswith("20261123_100000_") and "/" not in nome[16:] and ":" not in nome[16:]
    assert "_SCWM_MON" in nome


def test_prints_alem_do_teto_ficam_so_na_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "MAX_PRINTS_EMBUTIDOS", 2)
    pngs = []
    for i in range(4):
        p = tmp_path / f"p{i}.png"
        p.write_bytes(b"x" * 10)
        pngs.append(p)
    emb = relatorio._embutir(pngs)
    assert [u is not None for _, u in emb] == [True, True, False, False]
    monkeypatch.setattr(relatorio, "MAX_PRINTS_EMBUTIDOS", 99)
    monkeypatch.setattr(relatorio, "MAX_BYTES_EMBUTIDOS", 25)
    assert [u is not None for _, u in relatorio._embutir(pngs)] == [True, True, False, False]
