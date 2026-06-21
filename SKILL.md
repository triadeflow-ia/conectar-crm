---
name: conectar-crm
description: "Conecta formulários de captação de um cliente (WordPress/Elementor e/ou quiz InLead) ao CRM dele no GoHighLevel, via n8n. Cria credencial encrypted + workflow + planilha de backup + campos de rastreamento, com dedupe, Mídia (Pago/Orgânico), Origem do Lead e aviso de erro. Use quando o usuário pedir pra ligar/integrar o formulário ou quiz de um cliente ao CRM/HUB. Provisiona um cliente novo com poucos comandos a partir das keys (location_id + PIT)."
risk: medium
source: triadeflow
---

# Conectar CRM — Form (WordPress/InLead) → GoHighLevel via n8n

Motor reutilizável que recebe leads de formulário (Elementor Pro) e quiz (InLead) e cria/atualiza o contato no GHL do cliente, com rastreamento completo. Piloto validado: Dra. Gabriely (2026-06-20).

## Arquitetura
- **1 workflow n8n por cliente** (template duplicado). Webhooks: `/<slug>-wordpress` e `/<slug>-inlead`.
- Fluxo: Webhook → Config → Extrair Campos → valida → Listar CFs → Mapear Campos (match por nome) → Buscar/Criar/Atualizar contato GHL → ramo de Backup Sheets.
- **PIT do GHL em credencial encrypted do n8n** (nunca no workflow).
- **Error Workflow global** (id em `ERROR_WF_ID` do env): qualquer falha avisa Telegram (+ WhatsApp opcional).
- **Backup Sheets**: 1 planilha por cliente, criada PELA credencial Google do n8n (`GS_CRED_ID` do env), por causa do escopo `drive.file` (planilha precisa ser criada pela própria credencial). Node é best-effort (não quebra o fluxo).

## Pré-requisitos (uma vez por ambiente)
**Se for um ambiente NOVO (n8n próprio), siga o `SETUP.md` primeiro.** Ele configura:
- `~/.secrets/n8n-triadeflow.env` com `N8N_BASE_URL`, `N8N_API_KEY`, `GS_CRED_ID`, `ERROR_WF_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (+ Evolution opcional).
- Error Workflow global criado e ativo (`build_error_wf.py`).
- Credencial Google Sheets conectada no n8n (OAuth) → `GS_CRED_ID`.
- Util de planilhas criado (`build_criar_planilha.py`).

## Inputs por cliente
- `slug` (curto, único — vira o path do webhook, ex `gabriely`)
- `nome` (display, ex "Gabriely de Boulos")
- `location_id` + `PIT` do GHL do cliente (peça ao usuário; PIT em Settings → Private Integrations)
- fontes a conectar (WordPress / InLead)

## Procedimento (executar em ordem)

1. **Salvar secrets do cliente** em `~/.secrets/clientes/<slug>.env`:
   ```
   LOCATION_ID=...
   PIT=...
   ```
   (chmod 600. Nunca passar PIT em linha de comando.)

2. **Validar o PIT**: `GET /locations/<loc>` e `/customFields` com o PIT. Confirma nome da conta + scope.

3. **AUDITAR NO MASS DISPATCH** (inviolável): `GET https://services.leadconnectorhq.com/workflows/?locationId=<loc>`. Listar os PUBLICADOS. Se algum puder **enviar mensagem ao criar contato**, PARAR e confirmar com o usuário antes de ativar. O motor cria contatos — nenhum WF publicado pode disparar msg em contact-created.

4. **Criar campos de rastreamento**: `python3 scripts/setup_rastreamento.py --slug <slug>` (idempotente: utm_*, Mídia, Origem do Lead).

5. **Criar planilha de backup**: garantir o util existe (`python3 scripts/build_criar_planilha.py`), depois `python3 scripts/build_criar_planilha.py "Backup Leads - <nome>"` → pega `SHEET_ID`. Adicionar `SHEET_ID=...` ao `<slug>.env`. (Planilha SEM aba custom — usa Sheet1 gid=0.)

6. **Gerar o template** (se ainda não): `python3 scripts/build_template.py`.

7. **Provisionar**: `python3 scripts/provisionar.py --slug <slug> --cliente "<nome>" --ativar`.
   Cria credencial encrypted + workflow + ativa. Devolve as URLs dos webhooks.

8. **Testar e2e**: POST payload fake no `/<slug>-wordpress` (com `fields[name][title]`, `fields[telefone][title]` — sem title o motor marca inválido). Verificar contato criado no GHL + Backup Sheets. **Deletar o contato de teste.**

9. **Entregar ao usuário** as URLs + instruções de plug (abaixo).

## Plugar nas fontes (ação humana, guiar o usuário)
- **WordPress (Elementor Pro)**: editar o form no Elementor → aba Conteúdo → **Ações Após o Envio** → adicionar **Webhook** → colar `https://n8n.triadeflow.com.br/webhook/<slug>-wordpress` → Atualizar. (O Elementor só dispara na página publicada, não no preview.)
- **InLead (quiz)**: Integrações/Webhook do quiz → colar `https://n8n.triadeflow.com.br/webhook/<slug>-inlead`.
- **Anúncios (pré-req do gestor de tráfego)**: a URL de destino do anúncio precisa ter UTMs (`utm_source/medium/campaign/content/term`) — no Meta, campo "Parâmetros de URL" com macros `{{campaign.name}}` etc. Sem isso não há como classificar Pago.

## Como o rastreamento é preenchido (automático)
- **UTMs**: WordPress e InLead mandam `utm_*` com os mesmos nomes → gravados nos CFs `utm_*`.
- **Mídia**: tem `utm_campaign` e não-orgânico → `Pago`; senão `Orgânico`. (+ tag `midia-pago`/`midia-organico`)
- **Origem do Lead** (lista igual Talentus): prioridade — `utm_campaign` → `Trafego Pago`; senão popup site → `Pop-up Pagina`; senão (inlead/whats) → `Organico`.
- **InLead**: o Extrair limpa o ruído (`tracking.*`, `score*`, `responses*`, botões `clicked`, `code`) e faz de-para das etapas do quiz (`etapa_01_genero`→Gênero, etc). O de-para de etapas é específico por cliente — ajustar `DEPARA_QUIZ` no `build_template.py` conforme o quiz.

## Scripts
- `build_template.py` → gera `template-workflow.json` (placeholders __SLUG__ __LOCATION_ID__ __CLIENTE__ __NOME_WF__ __CRED_ID__ __CRED_NAME__ __SHEET_ID__ __ERROR_WF_ID__).
- `setup_rastreamento.py --slug` → cria CFs de rastreamento (idempotente).
- `build_criar_planilha.py [nome]` → cria o util / cria planilha via MAU.
- `build_error_wf.py` → cria o Error Workflow global (uma vez).
- `provisionar.py --slug --cliente [--ativar]` → credencial + workflow.

## Gotchas
- Re-aplicar o motor: o ID do workflow/credencial muda; o webhook path (slug) é estável. Antes de re-provisionar, **deletar TODOS** os workflows com o mesmo nome + suas credenciais (senão duplica no mesmo path e o antigo responde). Usar parsing `json.loads(..., strict=False)` (a list de workflows pode ter control chars).
- GHL não converte `dataType` de CF via PUT — pra virar SINGLE_OPTIONS, deletar e recriar.
- Python urllib falha SSL no Mac → usar `curl` (CA do sistema). Segredos via stdin (`--data-binary @-`), nunca em argv.
