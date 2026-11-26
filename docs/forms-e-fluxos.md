# Microsoft Forms e fluxos do Power Automate

## 1. O formulário

Formulário já montado no Microsoft Forms (conta do analista). Configurações: só pessoas da organização respondem; o email do
solicitante vem do login (`responder`), sem campo. Ele **ramifica por seção**:

| Seção | Pergunta | Obrigatória | Regra |
|---|---|---|---|
| (início) | Tipo de solicitação: `Criação de usuário` / `Modificação de acesso` | sim | escolhe a seção |
| Criação de usuário | IGG do novo usuário | sim | letra + 7 dígitos (L1234567), conferido pelo sistema |
| | Usuário de referência (IGG) | sim | o ZBR dele (lista semanal do O97) é o perfil do novo usuário |
| | Justificativa | sim | — |
| Modificação de acesso | IGG do usuário | sim | idem |
| | Transações | sim | uma ou várias, separadas por vírgula, `;` ou linha; máx. 10 |
| | Justificativa | sim | — |

### Formulário bilíngue (PT / EN, 26/11/2026)

Um formulário só, com o texto em **português e inglês na mesma linha** (decisão do analista; alternativas descartadas: formulário
dedicado em inglês, que duplicaria IDs de pergunta e fluxo, e seleção de idioma com seções duplicadas):

- título e descrição do formulário (português, depois inglês no parágrafo seguinte) e a mensagem de agradecimento;
- títulos das perguntas e das seções: `Tipo de solicitação / Request type`, `Criação de usuário / User creation`,
  `Modificação de acesso / Access modification`, `IGG do usuário / User IGG`, `Usuário de referência (IGG) / Reference user (IGG)`,
  `Justificativa / Justification`, `Transações / Transactions`;
- subtítulos: o texto em português que já existia, uma quebra de linha e a tradução (a pergunta 7 mantém o negrito do `OBS:` e ganha o `NOTE:`);
- opções da pergunta 1: `Criação de usuário / User creation` e `Modificação de acesso / Access modification`.

Como mexer só em texto não muda os IDs das perguntas, o fluxo do Power Automate e o `CHAVES` do `resposta.py` não mudam. O tipo é lido
pelo começo do texto (`ler_tipo`: "cria"/"creat" e "modif"), então **o português deve vir primeiro** na opção (e mesmo o inglês primeiro
funciona). Os e-mails de relatório continuam em português (só o analista os recebe).

**A criação não pede transações**: o perfil é o ZBR do usuário de referência. Sem transações não há o que simular: o relatório
sai com a situação `SEM ANÁLISE` e a request de criação segue as demais guardas (ver `docs/ARQUITETURA.md`).

O Forms não valida formato de texto: IGG, transações e limites são conferidos pelo sistema (`seguranca.py`). O Forms não tem
API pública de criação: o formulário foi montado à mão (o prompt de `docs/prompt-cowork-forms.md` descreve o mesmo desenho).

### Chaves da resposta

O fluxo grava a resposta **crua**: cada pergunta é uma chave com o ID que o Forms lhe deu. `resposta.py` (`CHAVES`, `ID_TIPO`)
traduz os IDs; os nomes legíveis (`criacao_igg`, `modificacao_transacoes`, `igg`...) continuam valendo para testes e
reprocessamento. Se o formulário for recriado ou ganhar pergunta, os IDs mudam: rodar o fluxo uma vez, ler a saída do
*Compose* no histórico e atualizar `CHAVES`.

| Chave no JSON | Conteúdo |
|---|---|
| `id_resposta` | Response Id (adicionado pelo *Compose*) |
| `responder` | email do solicitante |
| `submitDate` | envio, em UTC, `MM/dd/yyyy h:mm:ss tt` |
| `re72ac69...` | tipo de solicitação |
| `r1b4568cc...` / `r886c8288...` / `r4e7aee54...` | Criação: IGG / referência / justificativa |
| `rd5822024...` / `rf821d5f8...` / `r4a2c00f9...` | Modificação: IGG / transações / justificativa |

Há outras três chaves (`r40187b6...`, `rb6a15ffc...`, `r2e05578a...`) que vêm vazias e o sistema ignora. O `solicitante_nome`
não vem do Forms (fica vazio).

## 2. Fluxo "Gestao Usuarios - Resposta do Forms para SharePoint" (montado e LIGADO em 23/11/2026)

Ambiente **CPX - EP - SAP_Automation - PROD**.

1. *When a new response is submitted* (Microsoft Forms) → o formulário acima.
2. *Get response details* (mesmo formulário, `Response Id` do gatilho).
3. *Compose*: `@{addProperty(outputs('Get_response_details')?['body'], 'id_resposta', triggerOutputs()?['body/resourceData/responseId'])}`
   (a resposta crua mais o `id_resposta`).
4. *Create file* (SharePoint, site TEPBR-FINANCE): pasta
   `/1_9_SAP/2 - Melhorias e Projetos/7 - Automações/Gestao Usuarios/Solicitacoes de Acesso/@{formatDateTime(utcNow(), 'MM_yy')}`, nome
   `@{formatDateTime(utcNow(), 'yyyyMMdd_HHmmss')}_@{<Response Id>}.json`, conteúdo `@{outputs('Compose')}`.
   A pasta do mês é criada pelo próprio *Create file*; data e hora são em **UTC** (só dão nome ao arquivo).

O vigia lê a pasta inteira (`rglob`), então a subpasta do mês não importa. A conexão do Forms precisa estar ativa na conta
que roda o fluxo; se o *OAuth* abrir em popup bloqueado, liberar popups no navegador.

Texto livre do respondente entra no JSON sem aspas montadas à mão (é a saída do Forms serializada pelo Power Automate), então o
escape é dele. `resposta.py` ainda recusa JSON inválido (fase `RECUSADA`).

## 3. Fluxo "Gestao Usuarios - Relatorio por email" (montado e LIGADO em 23/11/2026)

Ambiente **CPX - EP - SAP_Automation - PROD**. Criado com *Save As* do fluxo *SOX Insumos - Relatorio lock-users por email*
(que não foi alterado) e adaptado no editor. Quatro ações, como no original:

1. *When a file is created (properties only)* (SharePoint, site TEPBR-FINANCE, biblioteca *1.9 - SAP*), pasta
   `/1_9_SAP/2 - Melhorias e Projetos/7 - Automações/Gestao Usuarios/Relatorios` (inclui subpastas; não cruza com a pasta `Relatorios` do
   lock-users), condição de gatilho `@endsWith(triggerOutputs()?['body/{FilenameWithExtension}'], '.html')` (ignora os `.png` e
   o `.tmp`).
2. *Get file content* (`@triggerBody()?['{Identifier}']`, sem inferir tipo) → *Compose*
   `@base64ToString(body('Get_file_content')?['$content'])`.
3. *Send an email (V2)*: **To** o analista (`gabriel.perrota@external.totalenergies.com`), **CC `vinicius.monteiro@totalenergies.com`** (Vinicius Monteiro; em 23/11/2026 o
CC tinha sido tirado por decisão do analista e em 26/11/2026 voltou só com ele; decisão anterior:
   23/11/2026), **Subject** `@substring(triggerOutputs()?['body/{FilenameWithExtension}'],16,sub(length(triggerOutputs()?['body/{FilenameWithExtension}']),21))`
   (o nome do arquivo sem os 16 primeiros caracteres `AAAAMMDD_HHMMSS_` e sem `.html`), **Body** a saída do *Compose*.

**Como o relatório se encaixa (`relatorio.py`):** o HTML se chama `AAAAMMDD_HHMMSS_<assunto>.html` (caracteres que o SharePoint não
aceita viram `_`) e é gravado **por último** (via `.tmp` + troca): é ele que dispara o fluxo. Os **prints vão embutidos no corpo**
em base64, como no relatório do lock-users, em vez de anexos: o editor do Power Automate não permite montar a lista de anexos
sem uma sequência frágil de ações (listar a pasta, filtrar, laço, variável). Há um teto de 16 prints e ~4 MB de PNG por
e-mail; o que passar fica só na pasta (o HTML avisa). Os PNG originais continuam na pasta do relatório.

**Como foi editado:** o *Code view* das ações é **só leitura** nesta versão do editor (mensagem *Cannot edit in read-only
editor*). O campo *Folder* do gatilho é um editor de texto rico (Lexical): clique, Ctrl+A e `keyboard.insert_text`. O CC se tira
com o botão *Remove parameter 'CC' and its value* (achar pelo rótulo acessível, não por posição) e se põe de volta em
*Advanced parameters* ("Showing 1 of 6" › marcar CC), digitando o e-mail e escolhendo a sugestão do diretório. O *Flow checker* mostra 0 erros
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
