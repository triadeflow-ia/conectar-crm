# SETUP — instalar a skill conectar-crm num ambiente novo

Guia de primeira instalação (uma vez por ambiente/n8n). Depois disso, é só invocar a skill `conectar-crm` no Claude Code pra cada cliente.

## 0. Pré-requisitos
- **Claude Code** instalado.
- **python3** e **curl** (padrão no Mac/Linux).
- Uma instância **n8n própria** (com a credencial Google Sheets disponível como integração).
- Por cliente: acesso ao **GoHighLevel** (location_id + Private Integration Token).

## 1. Instalar a skill
Copie a pasta `conectar-crm/` inteira para:
```
~/.claude/skills/conectar-crm/
```
(No Claude Code dela, a skill aparece automaticamente.)

## 2. Pegar a API key do n8n dela
No n8n: **Settings → n8n API → Create API key**. Copie a key e a URL base (ex `https://n8n.suaempresa.com`).

## 3. Criar o arquivo de configuração (um por ambiente/n8n)
Crie `~/.secrets/conectar-crm/<conta>.env` (ex `triadeflow.env`, `epelicula.env`) com:
```
N8N_BASE_URL=https://SEU-n8n.com
N8N_API_KEY=<a api key do passo 2>
GS_CRED_NAME=Google Sheets
# preenchidos nos passos seguintes:
GS_CRED_ID=
ERROR_WF_ID=
# alerta de erro (Telegram obrigatorio; WhatsApp opcional):
TELEGRAM_BOT_TOKEN=<token do @BotFather>
TELEGRAM_CHAT_ID=<seu id no @userinfobot>
# opcional WhatsApp via Evolution:
# EVOLUTION_URL=
# EVOLUTION_APIKEY=
# ALERT_WHATSAPP=55DDDNUMERO
```
```
mkdir -p ~/.secrets/conectar-crm && chmod 600 ~/.secrets/conectar-crm/<conta>.env
```

**Multi-ambiente:** antes de rodar a skill/scripts, aponte para o ambiente desejado:
```
export CONECTAR_CRM_ENV=~/.secrets/conectar-crm/<conta>.env
```
Assim vários n8n (clientes/ambientes diferentes) convivem sem um sobrescrever o outro. Se `CONECTAR_CRM_ENV` não for definido, o padrão é `~/.secrets/n8n-triadeflow.env`.

## 4. Conectar a credencial Google Sheets no n8n
No n8n dela: **Credentials → Add → Google Sheets OAuth2 API** → Sign in with Google (a conta que vai guardar as planilhas de backup) → salvar.
Abra a credencial e copie o **ID** (da URL `.../credentials/<ID>`). Coloque em `GS_CRED_ID=` no arquivo do passo 3.
> A conta Google logada aqui precisa ser a MESMA que cria as planilhas (a skill cria via essa credencial, então o acesso é garantido).

## 5. Criar o Error Workflow global (alerta de erro)
```
python3 ~/.claude/skills/conectar-crm/scripts/build_error_wf.py
```
Copie o `ERROR_WF_ID` que ele imprime e coloque em `ERROR_WF_ID=` no arquivo do passo 3.

## 6. Criar o utilitário de planilhas
```
python3 ~/.claude/skills/conectar-crm/scripts/build_criar_planilha.py
```

## Pronto
Agora, no Claude Code dela, é só pedir: **"conecta o formulário do cliente X no CRM"** (ou invocar a skill `conectar-crm`) e seguir o procedimento do `SKILL.md` — informando `slug`, `nome`, `location_id` e `PIT` do cliente.

### Observações
- Se pular o passo 4 (sem `GS_CRED_ID`), a skill funciona sem backup Sheets (só GHL).
- Se pular o passo 5 (sem `ERROR_WF_ID`), funciona sem aviso de erro.
- O de-para das etapas do quiz InLead (`DEPARA_QUIZ` em `scripts/build_template.py`) é específico por cliente — ajuste conforme as perguntas do quiz de cada um.
