# User-management-forms — instruções para o Claude

Análise de risco de pedidos de acesso SAP feitos pelo Microsoft Forms (TotalEnergies EP Brasil). Analista: `L1170904`.
Mapa: `docs/ARQUITETURA.md`. Forms e Power Automate: `docs/forms-e-fluxos.md`.
Projetos irmãos usados como referência de padrões (nada é importado deles): `C:\Users\L1170904\lock-users` (request no GRC,
SU01D, relatório por email) e `C:\dev\sox-automation` (Risk Analysis, SUIM, Forms, guardas).

## Regras invioláveis (só o usuário muda, e só explicitamente)

1. **SAP (E1P e O97) é SOMENTE LEITURA**: SU01D, SUIM e o *User x Business Roles Report*. Nada é gravado no SAP.
2. **GRC: a única escrita é a request de criação de usuário**, e só para usuário que **não existe** no E1P (relido antes do
   Submit). Usuário que já existe = aviso, nunca request. Risk Analysis só roda o relatório, nunca salva. **Única exceção
   (analista, 25/11/2026):** a variante `EP_SOD_2019_BRTEP` do passo 1 da simulação, salva UMA vez por `scripts/criar_variante_grc.py`;
   a rotina só a seleciona em *Saved Variants* e nunca clica em Save (`wd.PROIBIDOS`).
2a. **Análise de risco no GRC sempre com Rule Set `EP - SOD 2019`** (conferido na tela antes de seguir; nunca o padrão
   *Total Worldwide - Global Rule Set*) e com **Risk from Simulation only** marcada (só os riscos que a role traz).
2b. **A filial é só a BR-TEP**: o report do O97 roda sempre com User Group `BR-TEP` e Connector `E1PCLNT010`.
3. **Dry-run é o padrão**; criar request exige `--executar`. Disjuntor por rodada.
4. **Na dúvida não age**: leitura incerta, simulação que falhou, ZBR ambíguo = aviso para um humano. Simulação com erro nunca vale "sem risco".
5. **Credenciais nunca passam pelo código** (SSO feito pelo analista na janela da automação). Sem senha ou token no repositório.
6. **Nunca versionar evidência ou dado** (prints, Excel, respostas do Forms, estado, lista de ZBR).
7. **SharePoint: só se grava em `Insumos - Automação`.**
8. **Perguntar antes** de assumir tela ou regra de negócio, baixar arquivo ou instalar pacote.

## Como trabalhar

- Código, comentários e commits em **português**. Só commitar/enviar quando o usuário pedir.
- Lógica de decisão em funções puras (`decisao.py`, `analise.py`, `seguranca.py`); SAP/GRC atrás de `portas.py`.
- Regra nova ou alterada = teste novo. Testes: `.venv\Scripts\python.exe -m pytest -q`.
- Pontos em aberto da especificação: `docs/ARQUITETURA.md`, seção 11.
