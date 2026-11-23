# Microsoft Forms e fluxos do Power Automate

## 1. O formulário

Nome sugerido: **"Solicitação de acesso SAP (E1P)"**. Configurações: *Only people in my organization can respond*,
*Record name* ligado (o nome e o email do solicitante vêm do login, sem campo), uma resposta por envio.

| # | Pergunta | Tipo | Obrigatória | Regra |
|---|---|---|---|---|
| 1 | Tipo de solicitação | Escolha: `Criação de usuário`, `Modificação de acesso` | sim | ramifica |
| 2 | Usuário de referência (IGG) | Texto curto | sim | **só aparece em Criação** (ramificação) |
| 3 | IGG do usuário | Texto curto | sim | letra + 7 dígitos (ex.: L1234567), conferido pelo sistema |
| 4 | Transações | Texto longo | sim | uma ou várias, separadas por vírgula, `;` ou linha (ex.: FB01, FB02); máx. 10 |
| 5 | Justificativa | Texto longo | sim | — |

Ramificação (*Branching*): na pergunta 1, `Criação de usuário` → pergunta 2; `Modificação de acesso` → pergunta 3.
A referência vem antes do IGG porque no Forms só pergunta de escolha ramifica: com o IGG no meio, não haveria como mostrar a
referência só na Criação sem duplicar a pergunta do IGG.

O Forms não valida formato de texto (só números): IGG, transações e limites são conferidos pelo sistema (`seguranca.py`).
O Forms não tem API pública de criação: o formulário é montado à mão ou pelo Claude Cowork, com o prompt de
`docs/prompt-cowork-forms.md`.

## 2. Fluxo "Gestao Usuarios - Resposta do Forms para SharePoint"

Ambiente **CPX - EP - SAP_Automation - PROD**.

1. *When a new response is submitted* (Microsoft Forms) → formulário acima.
2. *Get response details* (mesmo formulário, `Response Id` do gatilho).
3. *Compose* com o JSON abaixo (as chaves são as que `resposta.py` lê; os valores vêm do conteúdo dinâmico).
4. *Create file* (SharePoint, site TEPBR-FINANCE): pasta
   `/1_9_SAP/1 - SOX/Insumos - Automação/Solicitacoes de Acesso/` +
   `formatDateTime(convertFromUtc(formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ'),'E. South America Standard Time'),'MM_yy')`,
   nome `concat(formatDateTime(convertFromUtc(formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ'),'E. South America Standard Time'),'yyyyMMdd_HHmmss'), '_', <Response Id>, '.json')`,
   conteúdo = saída do *Compose*.

Atenção ao erro conhecido do `convertFromUtc` com `+00:00` (ver `docs/fluxos-power-automate.md` do sox-automation): sempre
formatar a data antes de converter, como acima.

```json
{
  "id_resposta": "<Response Id>",
  "enviado_em": "<Submission time>",
  "solicitante_nome": "<Responders' Name>",
  "solicitante_email": "<Responders' Email>",
  "tipo": "<Tipo de solicitação>",
  "igg": "<IGG do usuário>",
  "usuario_referencia": "<Usuário de referência (IGG)>",
  "transacoes": "<Transações>",
  "justificativa": "<Justificativa>"
}
```

Texto livre do respondente entra no JSON: no *Compose*, use o conteúdo dinâmico dentro das aspas (o Power Automate escapa).
`resposta.py` também recusa JSON inválido (fase `RECUSADA`).

## 3. Fluxo "Gestao Usuarios - Relatorio por email" (montado e LIGADO em 23/11/2026)

Ambiente **CPX - EP - SAP_Automation - PROD**. Criado com *Save As* do fluxo *SOX Insumos - Relatorio lock-users por email*
(que não foi alterado) e adaptado no editor. Quatro ações, como no original:

1. *When a file is created (properties only)* (SharePoint, site TEPBR-FINANCE, biblioteca *1.9 - SAP*), pasta
   `/1_9_SAP/1 - SOX/Insumos - Automação/Relatorios Gestao Usuarios` (inclui subpastas; não cruza com a pasta `Relatorios` do
   lock-users), condição de gatilho `@endsWith(triggerOutputs()?['body/{FilenameWithExtension}'], '.html')` (ignora os `.png` e
   o `.tmp`).
2. *Get file content* (`@triggerBody()?['{Identifier}']`, sem inferir tipo) → *Compose*
   `@base64ToString(body('Get_file_content')?['$content'])`.
3. *Send an email (V2)*: **To** o analista (`gabriel.perrota@external.totalenergies.com`), **sem CC** (decisão do analista,
   23/11/2026), **Subject** `@substring(triggerOutputs()?['body/{FilenameWithExtension}'],16,sub(length(triggerOutputs()?['body/{FilenameWithExtension}']),21))`
   (o nome do arquivo sem os 16 primeiros caracteres `AAAAMMDD_HHMMSS_` e sem `.html`), **Body** a saída do *Compose*.

**Como o relatório se encaixa (`relatorio.py`):** o HTML se chama `AAAAMMDD_HHMMSS_<assunto>.html` (caracteres que o SharePoint não
aceita viram `_`) e é gravado **por último** (via `.tmp` + troca): é ele que dispara o fluxo. Os **prints vão embutidos no corpo**
em base64, como no relatório do lock-users, em vez de anexos: o editor do Power Automate não permite montar a lista de anexos
sem uma sequência frágil de ações (listar a pasta, filtrar, laço, variável). Há um teto de 16 prints e ~4 MB de PNG por
e-mail; o que passar fica só na pasta (o HTML avisa). Os PNG originais continuam na pasta do relatório.

**Como foi editado:** o *Code view* das ações é **só leitura** nesta versão do editor (mensagem *Cannot edit in read-only
editor*). O campo *Folder* do gatilho é um editor de texto rico (Lexical): clique, Ctrl+A e `keyboard.insert_text`. O CC se tira
com o botão *Remove parameter 'CC' and its value* (achar pelo rótulo acessível, não por posição). O *Flow checker* mostra 0 erros
e o aviso *This flow is off*.

**Teste real (23/11/2026, 11:25):** `processar` gravou um relatório de verdade na pasta vigiada (SU01, resultado OK). Em ~1 min o
fluxo disparou: 4 ações verdes em 1,5 s, e-mail **só para o analista**, sem CC, assunto `[gestao-usuarios] Modificação L1170904 - OK
(SU01)`. No Outlook na web o corpo renderizou completo (selo OK, tabelas, avisos e **10 imagens, todas carregadas**, entre elas as
capturas do SAP e do GRC).

**Roteamento na caixa (resolvido em 23/11/2026):** sem tratamento, o e-mail caía em *Ticket Review* (o fluxo *Tickets Review*, de
outro projeto, move para lá tudo que o analista manda para si mesmo). Em vez de mexer nesse fluxo, criei no Outlook uma **regra de
caixa de entrada** (server-side, Outlook na web › Configurações › Mail › Regras): *Gestão de usuários - relatórios da automação*,
condição **o assunto contém `[gestao-usuarios]`**, ação **mover para Automations › Gestão de usuários**, com *Stop processing more
rules*. Como a regra entrega a mensagem direto na pasta, o *Tickets Review* nem chega a vê-la (sem disputa entre fluxos, ao contrário
do que o lock-users precisou). Testado: o e-mail das 11:50 caiu direto em *Gestão de usuários* e o de teste anterior foi movido
para lá. Se mudar o prefixo do assunto (`relatorio.py`, `PREFIXO_ASSUNTO`), ajustar a regra.
