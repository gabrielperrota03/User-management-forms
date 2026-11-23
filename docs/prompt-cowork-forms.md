# Prompt para o Claude Cowork: criar o Microsoft Forms

Copie o bloco abaixo inteiro no Claude Cowork. Os títulos das perguntas e os textos das opções precisam ficar **exatamente**
como estão: o fluxo do Power Automate e o `resposta.py` dependem deles (ver `docs/forms-e-fluxos.md`).

---

```
Crie um formulário no Microsoft Forms (forms.office.com), na minha conta, seguindo exatamente a especificação abaixo.
Não altere, mova nem apague nenhum outro formulário. Não compartilhe o formulário com ninguém nem crie link de
colaboração: só deixe pronto e me devolva o link de resposta e o link de edição.

NOME DO FORMULÁRIO
Solicitação de acesso SAP (E1P)

DESCRIÇÃO DO FORMULÁRIO
Use este formulário para pedir a criação de um usuário no SAP E1P (client 010) ou para pedir novas transações para um
usuário que já existe. Cada pedido passa por uma análise de risco (SoD) automática antes de qualquer acesso ser
concedido. Informe as transações exatas de que você precisa (ex.: FB01).

CONFIGURAÇÕES (Settings)
- Who can fill out this form: Only people in my organization can respond
- Record name: LIGADO (o nome e o e-mail de quem responde são gravados automaticamente; NÃO crie pergunta de nome ou e-mail)
- One response per person: DESLIGADO (a mesma pessoa pode fazer vários pedidos)
- Accept responses: LIGADO
- Shuffle questions: DESLIGADO
- Mensagem de agradecimento (Customize thank you message): "Pedido recebido. A análise de risco é feita
  automaticamente e o time de acessos SAP entra em contato com o resultado."

PERGUNTAS (nesta ordem; todas obrigatórias, "Required" ligado)

1. Título: Tipo de solicitação
   Tipo: Choice (escolha única)
   Opções (exatamente, nesta ordem):
     - Criação de usuário
     - Modificação de acesso
   Subtítulo: Criação: o usuário ainda não existe no SAP E1P. Modificação: o usuário já existe e precisa de novas transações.

2. Título: Usuário de referência (IGG)
   Tipo: Text (resposta curta)
   Subtítulo: IGG de um colega que já tem o mesmo perfil de acesso no SAP. O novo usuário recebe o mesmo perfil
   (business role) dele. Formato: uma letra e 7 números, ex.: L1234567.
   Esta pergunta só aparece para "Criação de usuário" (ver RAMIFICAÇÃO).

3. Título: IGG do usuário
   Tipo: Text (resposta curta)
   Subtítulo: IGG da pessoa que vai receber o acesso (pode ser você ou outra pessoa). Formato: uma letra e 7 números,
   ex.: L1234567.

4. Título: Transações
   Tipo: Text com "Long answer" ligado
   Subtítulo: Uma ou mais transações SAP, separadas por vírgula, ponto e vírgula ou uma por linha. Máximo de 10 por
   pedido. Ex.: FB01, FB02

5. Título: Justificativa
   Tipo: Text com "Long answer" ligado
   Subtítulo: Para que você precisa desse acesso (atividade, processo, período).

RAMIFICAÇÃO (Branching, no menu "..." da pergunta 1 › Add branching)
- "Criação de usuário" → vai para a pergunta 2 (Usuário de referência (IGG))
- "Modificação de acesso" → vai para a pergunta 3 (IGG do usuário)
- Pergunta 2 → segue para a pergunta 3 (padrão)
- Perguntas 3, 4 e 5 → seguem na ordem (padrão); a 5 termina o formulário

NÃO FAÇA
- Não adicione validação, quiz, pontuação, seções extras, imagens nem perguntas além das 5 acima.
- Não troque os títulos das perguntas nem os textos das opções (são lidos por uma automação).
- Não conecte o formulário ao Excel nem crie fluxo do Power Automate.

QUANDO TERMINAR, ME RESPONDA COM
1. O link de resposta (Collect responses › Copy link) e o link de edição do formulário.
2. A lista das 5 perguntas exatamente como ficaram (título, tipo, obrigatória sim/não, opções).
3. A confirmação da ramificação: o que acontece ao escolher cada opção da pergunta 1.
4. As configurações como ficaram.
5. Um teste de pré-visualização (Preview), sem enviar: ao escolher "Modificação de acesso" a pergunta 2 não aparece;
   ao escolher "Criação de usuário" ela aparece.
```

---

## Depois que o Cowork terminar

1. Conferir a resposta dele com esta página (títulos, opções, ramificação, *Record name*).
2. Enviar uma resposta de teste de cada tipo (Criação e Modificação) com dados fictícios.
3. Montar o fluxo *Gestao Usuarios - Resposta do Forms para SharePoint* (`docs/forms-e-fluxos.md`, seção 2) apontando para
   este formulário.
