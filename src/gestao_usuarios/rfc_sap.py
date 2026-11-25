"""RFC para o SAP (só biblioteca padrão + sapnwrfc.dll do SAP GUI), SOMENTE LEITURA. Login por SNC (SSO do Windows), sem senha.

Copiada de `Desktop/Obsidian_Vault/rfc_sap.py` em 25/11/2026 (nada é importado de outro projeto), com três mudanças: sem pergunta
"Conectar?" nem prints; **lista fechada de funções e de tabelas** (regra 1: nada é gravado no SAP; `BAPI_USER_LOCK`/`CHANGE`
e qualquer outra função são recusadas por código); e `ler_tabela` (RFC_READ_TABLE) do extrator genérico.
Roteiro e prova de conceito: vault, `10 Projetos/Automações fora do PC`.
"""

import ctypes as C
import os
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

RFC_OK = 0

# Regra 1 (SAP somente leitura): só estas funções e só estas tabelas. Mudar a lista é decisão do analista.
FUNCOES_PERMITIDAS = frozenset({"BAPI_USER_GET_DETAIL", "RFC_READ_TABLE"})
TABELAS_PERMITIDAS = frozenset({"AGR_1251"})
PY64 = struct.calcsize("P") == 8
SNC_LIB_PADRAO = (
    r"C:\Program Files\SAP\FrontEnd\SecureLogin\lib\sapcrypto.dll"
    if PY64
    else r"C:\Program Files (x86)\SAP\FrontEnd\SecureLogin\lib\sapcrypto.dll"
)


# ---------------------------------------------------------------- estruturas da DLL
class RFC_ERROR_INFO(C.Structure):
    # SAP_UC = UTF-16 = c_wchar no Windows. A folga no fim evita estouro se a
    # versão da DLL tiver campos a mais.
    _fields_ = [
        ("code", C.c_int),
        ("group", C.c_int),
        ("key", C.c_wchar * 128),
        ("message", C.c_wchar * 512),
        ("abapMsgClass", C.c_wchar * 21),
        ("abapMsgType", C.c_wchar * 2),
        ("abapMsgNumber", C.c_wchar * 4),
        ("abapMsgV1", C.c_wchar * 51),
        ("abapMsgV2", C.c_wchar * 51),
        ("abapMsgV3", C.c_wchar * 51),
        ("abapMsgV4", C.c_wchar * 51),
        ("_folga", C.c_byte * 512),
    ]


class RFC_CONNECTION_PARAMETER(C.Structure):
    _fields_ = [("name", C.c_wchar_p), ("value", C.c_wchar_p)]


class ErroRFC(Exception):
    pass


class FuncaoNaoPermitida(ErroRFC):
    """A função ou a tabela não está na lista de leitura permitida (regra 1)."""


def conferir_chamada(funcao: str, entradas: dict | None = None) -> None:
    """Recusa, antes de qualquer contato com o SAP, o que não é leitura autorizada."""
    if funcao.upper() not in FUNCOES_PERMITIDAS:
        raise FuncaoNaoPermitida(f"função RFC fora da lista de leitura permitida: {funcao!r}")
    if funcao.upper() == "RFC_READ_TABLE":
        tabela = ((entradas or {}).get("QUERY_TABLE") or "").upper()
        if tabela not in TABELAS_PERMITIDAS:
            raise FuncaoNaoPermitida(f"tabela fora da lista de leitura permitida: {tabela!r}")


class Rfc:
    """Embrulho mínimo do SAP NW RFC SDK via ctypes."""

    def __init__(self):
        try:
            self.dll = C.WinDLL("sapnwrfc.dll")
        except OSError as e:
            raise ErroRFC(
                f"Não consegui carregar o sapnwrfc.dll ({e}). Python de "
                f"{'64' if PY64 else '32'} bits procura em C:\\Windows\\System32 "
                f"(64) ou SysWOW64 (32). Pode faltar alguma DLL que ele usa (icu*, libsapucum)."
            ) from e
        H, W, U, E = C.c_void_p, C.c_wchar_p, C.c_uint, C.POINTER(RFC_ERROR_INFO)
        assinaturas = {
            "RfcGetVersion": (W, [C.POINTER(U), C.POINTER(U), C.POINTER(U)]),
            "RfcOpenConnection": (H, [C.POINTER(RFC_CONNECTION_PARAMETER), U, E]),
            "RfcCloseConnection": (C.c_int, [H, E]),
            "RfcGetFunctionDesc": (H, [H, W, E]),
            "RfcCreateFunction": (H, [H, E]),
            "RfcDestroyFunction": (C.c_int, [H, E]),
            "RfcSetString": (C.c_int, [H, W, W, U, E]),
            "RfcInvoke": (C.c_int, [H, H, E]),
            "RfcGetStructure": (C.c_int, [H, W, C.POINTER(H), E]),
            "RfcGetTable": (C.c_int, [H, W, C.POINTER(H), E]),
            "RfcGetString": (C.c_int, [H, W, W, U, C.POINTER(U), E]),
            "RfcGetRowCount": (C.c_int, [H, C.POINTER(U), E]),
            "RfcMoveTo": (C.c_int, [H, U, E]),
            "RfcGetCurrentRow": (H, [H, E]),
            "RfcAppendNewRow": (H, [H, E]),
        }
        for nome, (ret, args) in assinaturas.items():
            f = getattr(self.dll, nome)
            f.restype, f.argtypes = ret, args
        self.conn = None

    # -- auxiliares
    @staticmethod
    def _falha(onde, err):
        msg = err.message.strip() or err.key.strip() or "sem mensagem"
        abap = err.abapMsgClass.strip()
        if abap:
            msg += f" [{abap} {err.abapMsgNumber.strip()}]"
        raise ErroRFC(f"{onde}: {msg} (código {err.code})")

    def _rc(self, onde, rc, err):
        if rc != RFC_OK:
            self._falha(onde, err)

    def versao(self):
        a, b, c = C.c_uint(), C.c_uint(), C.c_uint()
        texto = self.dll.RfcGetVersion(C.byref(a), C.byref(b), C.byref(c))
        return texto or f"{a.value}.{b.value}.{c.value}"

    # -- conexão
    def abrir(self, params: dict):
        arr = (RFC_CONNECTION_PARAMETER * len(params))()
        for i, (k, v) in enumerate(params.items()):
            arr[i].name, arr[i].value = k, str(v)
        err = RFC_ERROR_INFO()
        h = self.dll.RfcOpenConnection(arr, len(params), C.byref(err))
        if not h:
            self._falha("Abrir conexão", err)
        self.conn = h

    def fechar(self):
        if self.conn:
            err = RFC_ERROR_INFO()
            self.dll.RfcCloseConnection(self.conn, C.byref(err))
            self.conn = None

    # -- funções
    def chamar(self, funcao, entradas=None, tabelas=None):
        """Chama a função e devolve o handle (destruir com destruir())."""
        conferir_chamada(funcao, entradas)
        err = RFC_ERROR_INFO()
        desc = self.dll.RfcGetFunctionDesc(self.conn, funcao, C.byref(err))
        if not desc:
            self._falha(f"Descrição de {funcao}", err)
        f = self.dll.RfcCreateFunction(desc, C.byref(err))
        if not f:
            self._falha(f"Criar {funcao}", err)
        for nome, valor in (entradas or {}).items():
            self._rc(f"{funcao}.{nome}",
                     self.dll.RfcSetString(f, nome, valor, len(valor), C.byref(err)), err)
        for nome_tab, linhas in (tabelas or {}).items():
            t = C.c_void_p()
            self._rc(f"{funcao}.{nome_tab}",
                     self.dll.RfcGetTable(f, nome_tab, C.byref(t), C.byref(err)), err)
            for linha in linhas:
                row = self.dll.RfcAppendNewRow(t, C.byref(err))
                if not row:
                    self._falha(f"{funcao}.{nome_tab} nova linha", err)
                for campo, valor in linha.items():
                    self._rc(f"{funcao}.{nome_tab}.{campo}",
                             self.dll.RfcSetString(row, campo, valor, len(valor), C.byref(err)), err)
        self._rc(f"Executar {funcao}", self.dll.RfcInvoke(self.conn, f, C.byref(err)), err)
        return f

    def destruir(self, f):
        err = RFC_ERROR_INFO()
        self.dll.RfcDestroyFunction(f, C.byref(err))

    def _texto(self, container, campo):
        err = RFC_ERROR_INFO()
        buf = C.create_unicode_buffer(4096)
        n = C.c_uint()
        self._rc(f"Ler {campo}",
                 self.dll.RfcGetString(container, campo, buf, len(buf), C.byref(n), C.byref(err)), err)
        return buf.value

    def estrutura(self, f, nome, campos):
        err = RFC_ERROR_INFO()
        s = C.c_void_p()
        self._rc(f"Estrutura {nome}", self.dll.RfcGetStructure(f, nome, C.byref(s), C.byref(err)), err)
        return {c: self._texto(s, c) for c in campos}

    def tabela(self, f, nome, campos):
        err = RFC_ERROR_INFO()
        t = C.c_void_p()
        self._rc(f"Tabela {nome}", self.dll.RfcGetTable(f, nome, C.byref(t), C.byref(err)), err)
        n = C.c_uint()
        self._rc(f"Linhas de {nome}", self.dll.RfcGetRowCount(t, C.byref(n), C.byref(err)), err)
        linhas = []
        for i in range(n.value):
            self._rc(f"{nome}[{i}]", self.dll.RfcMoveTo(t, i, C.byref(err)), err)
            row = self.dll.RfcGetCurrentRow(t, C.byref(err))
            linhas.append({c: self._texto(row, c) for c in campos})
        return linhas


# ---------------------------------------------------------------- SAP Logon
def _caminho_de_url(url):
    p = urlparse(url)
    if p.scheme.lower() != "file":
        return None
    caminho = url2pathname(p.path)
    if p.netloc:  # file://servidor/compartilhamento
        caminho = "\\\\" + p.netloc + caminho
    return Path(caminho)


def _baixar_xml(url):
    """Lê o landscape central do SAP Logon (só um GET do XML de configuração)."""
    import ssl
    import urllib.request
    ctx = ssl.create_default_context()  # no Windows usa os certificados do sistema
    with urllib.request.urlopen(url, timeout=20, context=ctx) as r:
        return ET.fromstring(r.read())


def ler_landscape():
    """Lê os sistemas do SAP Logon (SAPUILandscape.xml local e os incluídos, inclusive por https)."""
    inicial = Path(os.environ.get("APPDATA", "")) / "SAP" / "Common" / "SAPUILandscape.xml"
    fila, vistos = [inicial], set()
    servicos, msgs, routers, ignorados = [], {}, {}, []
    while fila:
        arq = fila.pop(0)
        if str(arq) in vistos:
            continue
        vistos.add(str(arq))
        if isinstance(arq, str):  # URL http(s)
            try:
                raiz = _baixar_xml(arq)
            except Exception as e:
                ignorados.append(f"{arq}  ({e})")
                continue
        elif not arq.exists():
            ignorados.append(str(arq))
            continue
        else:
            raiz = ET.parse(arq).getroot()
        for inc in raiz.iter("Include"):
            url = inc.get("url", "")
            caminho = _caminho_de_url(url)
            if caminho:
                fila.append(caminho)
            elif url.lower().startswith(("http://", "https://")):
                fila.append(url)
            elif url:
                ignorados.append(url)
        for m in raiz.iter("Messageserver"):
            msgs[m.get("uuid")] = m.attrib
        for r in raiz.iter("Router"):
            routers[r.get("uuid")] = r.get("router", "")
        for s in raiz.iter("Service"):
            if s.get("type", "SAPGUI") == "SAPGUI":
                servicos.append(dict(s.attrib))
    return servicos, msgs, routers, ignorados


def montar_parametros(svc, msgs, routers, mandante, idioma, snc_lib):
    p = {"client": mandante, "lang": idioma}
    servidor = svc.get("server", "")
    msid = svc.get("msid")
    if msid and msid in msgs:  # balanceamento pelo message server
        ms = msgs[msid]
        p["mshost"] = ms.get("host", "")
        p["msserv"] = ms.get("port") or f"sapms{svc.get('systemid', '')}"
        p["sysid"] = svc.get("systemid", "")
        p["group"] = servidor or "PUBLIC"
    elif ":" in servidor:  # servidor de aplicação direto, porta 32NN
        host, porta = servidor.rsplit(":", 1)
        p["ashost"] = host
        p["sysnr"] = porta[-2:]
    else:
        raise ErroRFC(f"Não entendi o servidor da entrada '{svc.get('name')}': {servidor!r}")
    if svc.get("routerid") in routers and routers[svc["routerid"]]:
        p["saprouter"] = routers[svc["routerid"]]
    snc_nome = svc.get("sncname", "")
    if not snc_nome:
        raise ErroRFC(
            "Essa entrada do SAP Logon não tem SNC. O script não usa senha de propósito; "
            "escolha uma entrada com SNC (login sem senha)."
        )
    qop = svc.get("sncop", "9")
    p.update({
        "snc_mode": "1",
        "snc_partnername": snc_nome,
        "snc_qop": qop if qop in {"1", "2", "3", "8", "9"} else "9",
        "snc_lib": snc_lib,
    })
    return p




def conectar_por_sistema(sistema, mandante="010", idioma="EN", snc_lib=SNC_LIB_PADRAO):
    """Acha a entrada do SAP Logon pelo SID/nome e conecta (SNC, sem senha). Devolve (Rfc, entrada do SAP Logon)."""
    servicos, msgs, routers, ignorados = ler_landscape()
    alvo = sistema.lower()
    achados = [s for s in servicos
               if alvo == s.get("systemid", "").lower() or alvo in s.get("name", "").lower()]
    if len(achados) != 1:
        nomes = "\n  ".join(f"{s.get('systemid', '???'):5} {s.get('name', '')}" for s in achados)
        raise ErroRFC(f"'{sistema}' bateu com {len(achados)} entradas do SAP Logon.\n  {nomes}")
    svc = achados[0]
    params = montar_parametros(svc, msgs, routers, mandante, idioma, snc_lib)
    rfc = Rfc()
    rfc.abrir(params)
    return rfc, svc


# ---------------------------------------------------------------- leitura de tabela (RFC_READ_TABLE)
LARGURA_MAX = 512


def quebrar_filtro(filtro: str, largura: int = 72) -> list[str]:
    """O OPTIONS do RFC_READ_TABLE aceita linhas de até 72 caracteres: quebra nos espaços."""
    linhas, atual = [], ""
    for palavra in filtro.split(" "):
        candidato = f"{atual} {palavra}" if atual else palavra
        if len(candidato) <= largura:
            atual = candidato
        else:
            if atual:
                linhas.append(atual)
            if len(palavra) > largura:
                raise ErroRFC(f"trecho do filtro com mais de {largura} caracteres: {palavra[:40]}...")
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def cortar_linha(wa: str, layout: list[tuple[str, int, int]]) -> list[str]:
    """Corta a linha WA do RFC_READ_TABLE nas posições (nome, início, tamanho) devolvidas em FIELDS."""
    return [wa[ini:ini + tam].strip() for _, ini, tam in layout]


def ler_tabela(rfc: Rfc, tabela: str, campos: list[str], filtro: str = "") -> list[dict[str, str]]:
    """Lê uma tabela permitida inteira, só as colunas pedidas e com o filtro ABAP (WHERE). Confere a largura antes de ler."""
    entradas = {"QUERY_TABLE": tabela.upper()}
    tabelas = {"FIELDS": [{"FIELDNAME": c} for c in campos],
               "OPTIONS": [{"TEXT": x} for x in quebrar_filtro(filtro.strip())] if filtro.strip() else []}
    f = rfc.chamar("RFC_READ_TABLE", {**entradas, "NO_DATA": "X"}, tabelas)
    try:
        meta = rfc.tabela(f, "FIELDS", ["FIELDNAME", "OFFSET", "LENGTH"])
    finally:
        rfc.destruir(f)
    layout = [(m["FIELDNAME"], int(m["OFFSET"]), int(m["LENGTH"])) for m in meta]
    if max(ini + tam for _, ini, tam in layout) > LARGURA_MAX:
        raise ErroRFC(f"as colunas somam mais de {LARGURA_MAX} caracteres: peça menos colunas")
    f = rfc.chamar("RFC_READ_TABLE", entradas, tabelas)
    try:
        err = RFC_ERROR_INFO()
        h = C.c_void_p()
        rfc._rc("Tabela DATA", rfc.dll.RfcGetTable(f, "DATA", C.byref(h), C.byref(err)), err)
        n = C.c_uint()
        rfc._rc("Linhas de DATA", rfc.dll.RfcGetRowCount(h, C.byref(n), C.byref(err)), err)
        nomes = [nome for nome, _, _ in layout]
        saida = []
        for i in range(n.value):
            rfc._rc(f"DATA[{i}]", rfc.dll.RfcMoveTo(h, i, C.byref(err)), err)
            wa = rfc._texto(rfc.dll.RfcGetCurrentRow(h, C.byref(err)), "WA")
            saida.append(dict(zip(nomes, cortar_linha(wa, layout))))
        return saida
    finally:
        rfc.destruir(f)
