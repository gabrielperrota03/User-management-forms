"""GRC › Access Request › 'New or Change Account': cria o usuário novo com o ZBR do usuário de referência.
A ÚNICA escrita da aplicação no GRC. Só para usuário que NÃO existe no E1P (a decisão e a releitura do SAP estão em
processador.py / decisao.py; aqui há ainda a releitura imediatamente antes do Submit, `verificar`).

Mapeado ao vivo em 23/11/2026 (Chromium dedicado, GRC O97, sem submeter nada):
  Service map › Access Management › 'Access Request' (abre janela nova). Campos obrigatórios (*): Description, Request Type,
  Request For, User, Functional Area, User Group Name.
  Request Type = 'New or Change Account'; Request For = 'Other'; User = IGG + Enter: o GRC puxa First Name, Last Name e Email
  (aba User Details; obrigatórios e TRAVADOS: para um IGG que o GRC não conhece ficam vazios e o Submit não seria aceito).
  Functional Area 'EP- BRAZIL' e User Group Name 'BR-TEP' vêm ANTES do Add (sem Functional Area o GRC recusa:
  'Enter the value of Functional Area before adding roles').
  Aba User Access › Add › Role: diálogo 'Select Roles', critérios Role / Profile Name, Role Type, Functional Area (já preenchida);
  Role Type = 'Business Role' (o ZBR é uma Business Role) e Role / Profile Name = ZBR › Search › linha › seta Add › OK.
  A grade fica com 1 linha: Assignment = ZBR, Type 'Business Role', Valid To 31.12.9999, Assignment Approver (workflow de
  aprovação, diferente do Lock/Update), Provisioning Action 'Assign', Status 'Not Processed'.
  Submit › mensagem 'Request submitted successfully; the request number is N' (padrão do lock-users).
Travas: IGG e ZBR válidos; o formulário é relido e conferido contra o esperado ANTES do Submit; exatamente 1 linha na grade;
dados do usuário preenchidos; `verificar` (SAP de novo); Submit só com submeter=True; nunca repete o Submit.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import wd
from .capturas import capturar_pagina
from .erros import ErroValidacaoGrc, RequestBarrada, SubmitSemConfirmacao, UsuarioSemDadosNoGrc
from .grc_risco import _frame_do_service_map, _nwbc
from .sap_gui import TelaInesperada
from .seguranca import RE_IGG

log = logging.getLogger(__name__)

RE_ZBR = re.compile(r"^ZBR[A-Z0-9_&]{1,30}$")
_RE_NUMERO = re.compile(r"request number is\s+(\d+)", re.I)
_RE_ERRO = re.compile(r"Enter the value for [^\n]+")


@dataclass(frozen=True)
class ConfigGrcRequest:
    url: str
    functional_area: str = "EP- BRAZIL"
    user_group: str = "BR-TEP"
    tipo: str = "New or Change Account"
    request_for: str = "Other"
    tipo_role: str = "Business Role"
    aba: str = "Access Management"
    link: str = "Access Request"

    @classmethod
    def de_config(cls, cfg: dict) -> "ConfigGrcRequest":
        g, r = cfg["grc"], cfg.get("grc_request") or {}
        base = {"url": g["url"], "functional_area": g.get("functional_area", "EP- BRAZIL"),
                "user_group": g.get("user_group", "BR-TEP")}
        return cls(**{**base, **{k: v for k, v in r.items() if k in cls.__dataclass_fields__}})


# ------------------------------------------------------------------ funções puras

def numero_da_request(texto: str) -> str | None:
    m = _RE_NUMERO.search(texto or "")
    return m.group(1) if m else None


def erros_de_validacao(texto: str) -> list[str]:
    return _RE_ERRO.findall(texto or "")


def validar_entrada(igg: str, zbr: str, descricao: str) -> None:
    if not RE_IGG.match(igg or ""):
        raise RequestBarrada(f"IGG inválido para a request: {igg!r}")
    if not RE_ZBR.match(zbr or ""):
        raise RequestBarrada(f"ZBR inválido para a request: {zbr!r}")
    if not (descricao or "").strip():
        raise RequestBarrada("request sem descrição")


def conferir_formulario(lido: dict[str, str], c: ConfigGrcRequest, igg: str, descricao: str) -> list[str]:
    """Divergências entre o que a tela mostra e o que pretendemos enviar (vazia = pode seguir)."""
    esperado = {"Request Type": c.tipo, "Request For": c.request_for, "User": igg, "Functional Area": c.functional_area,
                "User Group Name": c.user_group, "Description": descricao.strip()}
    return [f"{k}: tela {lido.get(k)!r}, esperado {v!r}" for k, v in esperado.items()
            if (lido.get(k) or "").strip().upper() != v.upper()]


def conferir_grade(linhas: list[dict[str, str]], c: ConfigGrcRequest, zbr: str) -> list[str]:
    """A grade de acessos tem de ter UMA linha: o ZBR, como Business Role, para atribuir (Assign)."""
    if len(linhas) != 1:
        return [f"a grade tem {len(linhas)} linhas, esperado 1 (o ZBR): {[l.get('Assignment') for l in linhas]}"]
    l = linhas[0]
    esperado = {"Assignment": zbr, "Type": c.tipo_role, "Provisioning Action": "Assign"}
    erros = [f"{k}: tela {l.get(k)!r}, esperado {v!r}" for k, v in esperado.items()
             if (l.get(k) or "").strip().upper() != v.upper()]
    if (l.get("Valid To") or "").strip() not in ("31.12.9999", "30.12.9999"):
        erros.append(f"Valid To: tela {l.get('Valid To')!r}, esperado sem fim (31.12.9999)")
    return erros


def dados_do_usuario_completos(dados: dict[str, str]) -> list[str]:
    """Campos obrigatórios que o GRC deveria ter preenchido (vazio = o GRC não conhece a pessoa)."""
    return [k for k in ("First Name", "Last Name", "Email") if not (dados.get(k) or "").strip()]


def linha_do_resultado(linhas: list[dict[str, str]], zbr: str, tipo_role: str) -> int | None:
    """Número (1-based) da única linha do diálogo de roles que é o ZBR como Business Role; levanta se 0 ou mais de uma."""
    achadas = [i for i, l in enumerate(linhas, 1)
               if (l.get("Role Name") or "").strip().upper() == zbr.upper() and (l.get("Role Type") or "").strip() == tipo_role]
    if len(achadas) != 1:
        vistas = [(l.get("Role Name"), l.get("Role Type")) for l in linhas][:8]
        raise RequestBarrada(f"{zbr} não foi achada exatamente uma vez como {tipo_role} no GRC (achadas {len(achadas)}; "
                             f"resultado: {vistas})")
    return achadas[0]


# ------------------------------------------------------------------ formulário real

def _rotulo(frame, texto: str):
    """Campo pelo rótulo (label ct=L -> atributo f). Sem rótulo na tela (ex.: aba fechada) levanta na hora: o Playwright
    esperaria 30 s por um elemento que não vem (visto ao vivo em 23/11/2026)."""
    rotulos = frame.locator('label[ct="L"]').filter(has_text=re.compile(rf"^\s*{re.escape(texto)}\s*:?\s*$"))
    if rotulos.count() == 0:
        raise TelaInesperada(f"campo {texto!r} não está na tela")
    ident = rotulos.first.get_attribute("f", timeout=5000)
    if not ident:
        raise TelaInesperada(f"campo {texto!r} sem identificador")
    return frame.locator("#" + ident)


def _valor(campo) -> str:
    return (campo.evaluate("e => (e.value !== undefined && e.tagName === 'INPUT') || e.tagName === 'TEXTAREA' "
                           "? e.value : e.innerText") or "").strip()


class GrcRequestPlaywright:
    """Porta GrcRequest. `contexto` = contexto do Chromium dedicado (o mesmo da simulação)."""

    def __init__(self, contexto, c: ConfigGrcRequest, pasta_prints: Path | None = None, exigir_dados_usuario: bool = True):
        self.contexto, self.c, self.pasta_prints = contexto, c, pasta_prints
        self.exigir_dados_usuario = exigir_dados_usuario       # False só nos testes de tela, e então o Submit é impossível
        self.prints: list[Path] = []

    # --- abertura --------------------------------------------------------------------------------------------------
    def _abrir(self):
        nwbc = _nwbc(self.contexto, self.c.url)
        if "login.microsoft" in nwbc.url:
            raise wd.SessaoParada("o GRC pediu login (SSO): entre na janela do Chromium dedicado")
        nwbc.get_by_role("link", name=self.c.aba, exact=True).first.click()
        nwbc.wait_for_timeout(3000)
        links = _frame_do_service_map(nwbc).locator('a[ct="LN"]')
        alvo = [links.nth(i) for i in range(links.count()) if links.nth(i).inner_text().strip() == self.c.link]
        if len(alvo) != 1:
            raise TelaInesperada(f"link {self.c.link!r} não encontrado (ou repetido) no service map")
        with self.contexto.expect_page(timeout=60000) as nova:
            alvo[0].click()
        pagina = nova.value
        pagina.wait_for_load_state("load")
        fim = time.monotonic() + 60
        while time.monotonic() < fim:
            for f in pagina.frames:
                try:
                    if f.locator('label[ct="L"]', has_text="Request Type").count():
                        wd.aguardar(pagina, f, 1500)
                        return pagina, f
                except Exception:  # noqa: BLE001
                    continue
            pagina.wait_for_timeout(500)
        pagina.close(run_before_unload=False)
        raise TelaInesperada("o formulário Access Request não carregou")

    # --- preenchimento ---------------------------------------------------------------------------------------------
    def _dados_do_usuario(self, pagina, frame, limite_s: float = 30.0) -> dict[str, str]:
        """Depois do Enter no User, o GRC preenche First Name, Last Name e Email (aba User Details). Lê com espera e volta à aba
        User Access."""
        dados: dict[str, str] = {}
        try:
            wd.clicar_aba(pagina, frame, "User Details")
            fim = time.monotonic() + limite_s
            while time.monotonic() < fim:
                try:
                    dados = {k: _valor(_rotulo(frame, k)) for k in ("First Name", "Last Name", "Email")}
                except TelaInesperada:                         # a aba ainda não abriu (o clique pode se perder no round-trip)
                    wd.clicar_aba(pagina, frame, "User Details")
                    continue
                if not dados_do_usuario_completos(dados):
                    return dados
                pagina.wait_for_timeout(1000)
            return dados
        finally:
            wd.clicar_aba(pagina, frame, "User Access")

    def _adicionar_zbr(self, pagina, frame, zbr: str) -> None:
        wd.clicar_botao(pagina, frame, "Add")
        wd._visivel(frame, '[ct="POMNI"]', "Role").click()
        fim = time.monotonic() + 20
        while time.monotonic() < fim:                          # o diálogo 'Select Roles' demora um instante
            try:
                wd.campo_do_criterio(frame, "Role / Profile Name")
                break
            except TelaInesperada:
                pagina.wait_for_timeout(500)
        wd.escolher(pagina, frame, wd.campo_do_criterio(frame, "Role Type"), self.c.tipo_role)
        wd.digitar(pagina, frame, wd.campo_do_criterio(frame, "Role / Profile Name"), zbr)
        wd.clicar_botao(pagina, frame, "Search", 3000)
        t = wd.ler_tabela(pagina, frame, "Role Name")
        n = linha_do_resultado(t["linhas"], zbr, self.c.tipo_role)
        frame.locator(f'#{t["id"]} tr[rr="{n}"] td').nth(3).click()      # coluna Description (0 = seletor da linha)
        pagina.wait_for_timeout(800)
        frame.locator('[ct="B"][title="Add"]').last.click()               # seta: passa para 'Selected'
        wd.aguardar(pagina, frame, 2000)
        wd.clicar_botao(pagina, frame, "OK", 3000)

    def _preencher(self, pagina, frame, igg: str, zbr: str, descricao: str) -> dict:
        c = self.c
        wd.escolher(pagina, frame, _rotulo(frame, "Request Type"), c.tipo)
        wd.escolher(pagina, frame, _rotulo(frame, "Request For"), c.request_for)
        _rotulo(frame, "Description").fill(descricao)
        usuario = _rotulo(frame, "User")
        usuario.click()
        pagina.keyboard.press("Control+A")
        pagina.keyboard.type(igg)
        pagina.keyboard.press("Enter")                                    # o Enter faz o GRC puxar os dados do usuário
        wd.aguardar(pagina, frame, 2500)
        dados = self._dados_do_usuario(pagina, frame)
        faltam = dados_do_usuario_completos(dados)
        if faltam and self.exigir_dados_usuario:
            raise UsuarioSemDadosNoGrc(f"o GRC não preencheu {', '.join(faltam)} para {igg}: a pessoa não está no cadastro "
                                       "que o GRC consulta (campos obrigatórios e travados); nada foi enviado")
        wd.escolher(pagina, frame, _rotulo(frame, "Functional Area"), c.functional_area)
        wd.escolher(pagina, frame, _rotulo(frame, "User Group Name"), c.user_group)
        self._adicionar_zbr(pagina, frame, zbr)
        lido = {k: _valor(_rotulo(frame, k)) for k in ("Request Type", "Request For", "User", "Functional Area",
                                                        "User Group Name", "Description")}
        erros = conferir_formulario(lido, c, igg, descricao)
        grade = wd.ler_tabela(pagina, frame, "Assignment")
        erros += conferir_grade(grade["linhas"], c, zbr)
        if erros:
            raise RequestBarrada("formulário não confere com o esperado: " + "; ".join(erros))
        return dados

    def _print(self, pagina, nome: str) -> None:
        if self.pasta_prints is not None:
            p = capturar_pagina(pagina, self.pasta_prints / nome)
            if p:
                self.prints.append(p)

    def _submeter(self, pagina, frame) -> str:
        frame.locator('[ct="B"][title="Submit"]').click()                 # único clique em Submit do projeto
        fim = time.monotonic() + 90
        while time.monotonic() < fim:
            pagina.wait_for_timeout(1000)
            try:
                texto = frame.evaluate("document.body.innerText")
            except Exception:  # noqa: BLE001 - a página está navegando
                continue
            numero = numero_da_request(texto)
            if numero:
                return numero
            erros = erros_de_validacao(texto)
            if erros:
                raise ErroValidacaoGrc("o GRC recusou o Submit: " + "; ".join(erros) + " (nada foi criado)")
        raise SubmitSemConfirmacao("Submit clicado, mas a mensagem de sucesso não apareceu em 90 s: CONFERIR no Request Status "
                                   "antes de repetir")

    # --- porta -----------------------------------------------------------------------------------------------------
    def criar_usuario(self, igg: str, zbr: str, descricao: str, *, submeter: bool = True,
                      verificar: Callable[[], str | None] | None = None) -> str | None:
        """Preenche e confere o formulário. Com submeter=True faz o Submit e devolve o número da request; com
        submeter=False (ensaio) só preenche, confere, tira o print e devolve None. `verificar` roda com o formulário pronto,
        imediatamente antes do Submit: devolve o motivo de recusa ou None."""
        validar_entrada(igg, zbr, descricao)
        if submeter and not self.exigir_dados_usuario:
            raise ValueError("Submit é impossível com exigir_dados_usuario=False (modo de teste de tela)")
        pagina, frame = self._abrir()
        try:
            self._preencher(pagina, frame, igg, zbr, descricao)
            self._print(pagina, f"grc_request_{igg}_formulario.png")
            if verificar is not None:
                motivo = verificar()
                if motivo:
                    raise RequestBarrada(motivo)
            if not submeter:
                return None
            numero = self._submeter(pagina, frame)
            log.info("request %s criada: usuário %s, ZBR %s", numero, igg, zbr)
            self._print(pagina, f"grc_request_{igg}_{numero}.png")
            return numero
        finally:
            try:
                pagina.close(run_before_unload=False)
            except Exception:  # noqa: BLE001
                pass
