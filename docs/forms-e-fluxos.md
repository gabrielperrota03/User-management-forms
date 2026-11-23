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

## 3. Fluxo "Gestao Usuarios - Relatorio por email"

1. *When a file is created (properties only)* na pasta `/1_9_SAP/1 - SOX/Insumos - Automação/Relatorios Gestao Usuarios`
   (inclui subpastas), condição de gatilho `@equals(triggerOutputs()?['body/{FilenameWithExtension}'], 'relatorio.html')`.
2. *Get file content* do `relatorio.html` → *Compose* `base64ToString(body('Get_file_content')?['$content'])`.
3. *List folder* da mesma pasta → *Filter array* `endsWith(item()?['Name'], '.png')` → *Apply to each*: *Get file content* e
   *Append to array variable* `{"Name": nome, "ContentBytes": conteúdo}`.
4. *Get file content* do `assunto.txt` (gravado ao lado) para o assunto.
5. *Send an email (V2)*: corpo = Compose, anexos = a variável, destinatário = analista, CC fixo.

O `relatorio.html` é gravado **por último** (depois dos prints e do `assunto.txt`), via `.tmp` + troca, para o fluxo nunca ver a
pasta pela metade.

Roteamento na caixa: assunto começa com `[gestao-usuarios]` (ajustar o fluxo *Tickets Review*, como no lock-users).
