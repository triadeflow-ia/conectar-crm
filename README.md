# conectar-crm

Skill do Claude Code que conecta os formulários de captação de um cliente — **WordPress (Elementor Pro)** e **quiz (InLead)** — ao CRM dele no **GoHighLevel**, usando o **n8n** como motor. Provisiona um cliente novo a partir das chaves de acesso (`location_id` + token), com poucos comandos.

A partir de um lead que entra pelo formulário, a skill cria/atualiza o contato no CRM já com rastreamento de origem, evita duplicados e guarda uma cópia de segurança — tudo automático.

## O que ela faz

- **Recebe leads** de formulário Elementor Pro e de quiz InLead (dois webhooks por cliente)
- **Cria/atualiza o contato** no GoHighLevel, com dedupe por telefone/e-mail (não duplica)
- **Mapeia os campos** do formulário para os custom fields do cliente (match por nome)
- **Rastreamento automático:**
  - UTMs (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`)
  - **Mídia**: Pago ou Orgânico (derivado do UTM)
  - **Origem do Lead**: lista de seleção (Tráfego Pago, Pop-up Página, Orgânico, etc.)
- **Limpa o ruído do InLead** (tracking, score, respostas consolidadas, botões) e faz de-para das etapas do quiz
- **Backup em Google Sheets** (uma planilha por cliente, best-effort — não derruba o fluxo se falhar)
- **Aviso de erro** por Telegram (e WhatsApp opcional) via um Error Workflow global
- **Guardrail anti-disparo em massa**: antes de ativar, audita se algum workflow publicado dispara mensagem ao criar contato

## Arquitetura

```
WordPress (Elementor) ─┐
                       ├─► webhook n8n ─► Extrair ─► Mapear campos ─► GHL (cria/atualiza)
Quiz (InLead) ─────────┘                    │                         └─► oportunidade
                                            └─► Backup Google Sheets
                                          (falha em qualquer ponto → Error Workflow → Telegram/WhatsApp)
```

- **1 workflow n8n por cliente** (template duplicado). Webhooks: `/<slug>-wordpress` e `/<slug>-inlead`.
- **O token do GHL fica numa credencial encrypted do n8n** — nunca no corpo do workflow.
- Os scripts são **env-driven**: nenhum identificador de ambiente fica embutido no código.

## Requisitos

- [Claude Code](https://claude.com/claude-code)
- `python3` e `curl` (padrão em Mac/Linux)
- Uma instância **n8n** própria (com a integração Google Sheets disponível)
- Por cliente: acesso ao **GoHighLevel** (`location_id` + Private Integration Token)
- Opcional: bot do Telegram (para o aviso de erro), conta Google (para o backup em Sheets)

## Instalação

Clone direto na pasta de skills do Claude Code:

```bash
git clone https://github.com/triadeflow-ia/conectar-crm.git ~/.claude/skills/conectar-crm
```

Depois siga o **[SETUP.md](SETUP.md)** uma vez por ambiente (configura a API key do n8n, a credencial Google, o Error Workflow e o utilitário de planilhas).

## Uso

No Claude Code, peça em linguagem natural — por exemplo:

> conecta o formulário do cliente X no CRM

A skill pede o `slug`, o nome do cliente, o `location_id` e o token do GHL, e então:

1. salva as chaves do cliente localmente (`~/.secrets/clientes/<slug>.env`)
2. valida o token
3. **audita anti-disparo em massa** (não ativa se algum workflow publicado mandar mensagem ao criar contato)
4. cria os campos de rastreamento
5. cria a planilha de backup
6. provisiona o workflow (credencial + webhooks) e ativa
7. testa de ponta a ponta e limpa o lead de teste
8. entrega as URLs dos webhooks para você colar no Elementor/InLead

Também dá para rodar os scripts diretamente — veja `scripts/`.

## Estrutura

```
SKILL.md                      instruções da skill (lidas pelo Claude Code)
SETUP.md                      guia de primeira instalação por ambiente
scripts/
  build_template.py           gera o workflow template (parametrizado)
  template-workflow.json      template do workflow n8n
  provisionar.py              cria credencial + workflow do cliente
  setup_rastreamento.py       cria os custom fields de rastreamento (idempotente)
  build_criar_planilha.py     cria a planilha de backup pela credencial do n8n
  build_error_wf.py           cria o Error Workflow global (aviso de erro)
```

## Segurança

- Nenhum segredo é versionado. As chaves ficam em `~/.secrets/` (fora do repositório, no `.gitignore`).
- Tokens são passados para o `curl` via stdin, nunca em linha de comando.
- O token do GHL vive como credencial encrypted no n8n, fora do JSON do workflow.
- Antes de ativar qualquer cliente, a skill audita se há workflow publicado capaz de disparar mensagem ao contato — um lead novo nunca deve gerar envio em massa.

## Licença

MIT.

## Contato

Feito pela **Triadeflow**.

- Site: [triadeflow.com.br](https://triadeflow.com.br)
- Instagram: [@triadeflow.ia](https://instagram.com/triadeflow.ia)
- E-mail: contato@triadeflow.com.br
- Telefone: (11) 4863-4209
