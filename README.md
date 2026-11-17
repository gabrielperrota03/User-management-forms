# User-management-forms

Análise de risco automática de pedidos de acesso SAP (E1P) feitos por um Microsoft Forms.

Fluxo: Forms → Power Automate grava a resposta em JSON no OneDrive → vigia local (Python) → SUIM no E1P acha as single roles
de cada transação → GRC *Access Risk Analysis* com simulação para cada role → relatório HTML com prints por email.
Na **criação de usuário** (só se o usuário ainda não existe no SAP), cria a request no GRC com o ZBR do usuário de referência.

- Como funciona: [docs/ARQUITETURA.md](docs/ARQUITETURA.md)
- Formulário e fluxos do Power Automate: [docs/forms-e-fluxos.md](docs/forms-e-fluxos.md)

## Estado
Especificação e núcleo puro (validação, decisão, comparação de riscos, lista de ZBR, manifesto, orquestração) com testes.
A fazer: integrações reais com SAP (SU01D, SUIM, O97) e GRC (simulação e request), relatório, vigia e CLI.

## Instalar e testar
```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e . pytest
.venv\Scripts\python -m pytest
```
