#!/usr/bin/env python3
"""
Gera o workflow TEMPLATE "Form -> GHL" pro n8n (versao com backup Sheets + aviso de erro).
Derivado do modelo "Popup Talentus" (HYab7DN2kf3TZ4nv).

SEGURANCA: PIT do GHL NUNCA fica no workflow (credencial httpHeaderAuth encrypted).
Backup: cada lead vai tambem pra uma planilha Google (1 por cliente).
Aviso de erro: settings.errorWorkflow aponta pro Error Workflow GLOBAL (Telegram + WhatsApp).

Placeholders (a skill troca): __LOCATION_ID__ __CLIENTE__ __SLUG__ __NOME_WF__
                              __CRED_ID__ __CRED_NAME__ __SHEET_ID__ __ERROR_WF_ID__
"""
import json, os

REF = "/tmp/popup-talentus.json"
# credencial Google do n8n: parametrizada (provisionar.py substitui pelos valores do ambiente)
GS_CRED = {"googleSheetsOAuth2Api": {"id": "__GS_CRED_ID__", "name": "__GS_CRED_NAME__"}}


def ref_versions():
    v = {"webhook": 2, "code": 2, "if": 2, "httpRequest": 4.2, "googleSheets": 4.5}
    try:
        d = json.load(open(REF))
        for n in d.get("nodes", []):
            t = n["type"].split(".")[-1]
            if t in v:
                v[t] = n.get("typeVersion", v[t])
    except Exception:
        pass
    return v


V = ref_versions()

# ---------------- jsCodes ----------------

ORIGEM_WP = """return { json: { body: $json.body || {}, headers: $json.headers || {}, query: $json.query || {}, _origem: 'site-wordpress' } };"""
ORIGEM_INLEAD = """return { json: { body: $json.body || {}, headers: $json.headers || {}, query: $json.query || {}, _origem: 'inlead' } };"""

CONFIG = """// CONFIG DO CLIENTE - location_id (nao-secreto). O PIT vive na credencial do n8n.
return { json: Object.assign({}, $json, {
  location_id: '__LOCATION_ID__',
  cliente: '__CLIENTE__'
}) };"""

EXTRAIR = r"""// EXTRAIR CAMPOS - generico (template Form -> GHL)
const input = $json || {};
const body = input.body || {};
const headers = input.headers || {};
const origem = input._origem || 'form';

if (!body || Object.keys(body).length === 0) {
  return { json: { _skip: true, _nivel: 'bloqueio', _motivo: 'Payload vazio', _all_fields: {}, _campos_novos: [], tags: [] } };
}

function norm(s){ return (s||'').toString().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,''); }

const isStructured = Object.keys(body).some(k => k.startsWith('fields['));
const byTitle = {};
let allFields = {};

if (isStructured) {
  const ids = new Set();
  for (const k of Object.keys(body)) { const m = k.match(/^fields\[([^\]]+)\]\[id\]$/); if (m) ids.add(m[1]); }
  for (const fid of ids) {
    const title = (body['fields['+fid+'][title]'] || '').trim();
    const value = body['fields['+fid+'][value]'] || '';
    const type = body['fields['+fid+'][type]'] || '';
    if (type === 'step' || !title) continue;
    byTitle[title.toLowerCase()] = value;
    if (value !== '') allFields[title] = value;
  }
} else {
  const skip = ['date','time','page url','user agent','remote ip','form[id]','form[name]','form_id','form_name','action','referrer'];
  for (const [k,v] of Object.entries(body)) {
    if (skip.includes(k.toLowerCase()) || k.startsWith('No Label')) continue;
    if (k && v !== '' && v != null) { byTitle[k.trim().toLowerCase()] = v; allFields[k.trim()] = v; }
  }
}

function find(keys){ for (const [t,v] of Object.entries(byTitle)){ const tn=norm(t); if (keys.some(k=>tn.includes(norm(k)))) return v; } return ''; }

const nome = (body['fields[name][value]'] || find(['nome','name','seu nome']) || '').toString().trim();
const email = (body['fields[email][value]'] || find(['email','e-mail']) || '').toString().toLowerCase().trim();
const telRaw = (body['fields[phone][value]'] || find(['whatsapp','telefone','celular','phone']) || '').toString();

let d = telRaw.replace(/\D/g,'');
if (d.startsWith('55') && d.length >= 12) d = d.substring(2);
if (d.length === 10 && d.charAt(2) !== '9') d = d.substring(0,2) + '9' + d.substring(2);
const telefone = d.length >= 10 ? '+55'+d : (d.length > 0 ? '+'+d : '');

const formName = (body['form[name]'] || body['form_name'] || '').toString();
const tagForm = norm(formName).replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
const tags = ['origem-'+origem];
if (tagForm) tags.push(tagForm);

// tratamento InLead (quiz): limpar ruido + de-para das respostas pros campos do cliente
if (origem === 'inlead') {
  const DEPARA_QUIZ = {
    'etapa_01_genero': 'Gênero',
    'etapa_03_ja_fez_antes': 'Já fez harmonização antes',
    'etapa_04_o_que_incomoda': 'O que incomoda',
    'etapa_05_em_quais_dessas': 'Situações desconfortáveis',
    'etapa_06_faria': 'Disposição (Faria)'
  };
  const limpo = {};
  for (const [k, v] of Object.entries(allFields)) {
    const kl = k.toLowerCase();
    // ignorar ruido do InLead (tracking, score, responses consolidado, botoes clicados, code)
    if (v === 'clicked' || kl === 'code' || kl.startsWith('tracking') || kl.startsWith('score')
        || kl.startsWith('responses') || kl.startsWith('botao')) continue;
    if (DEPARA_QUIZ[kl]) { limpo[DEPARA_QUIZ[kl]] = v; continue; }
    if (/^etapa_02_/i.test(kl)) { limpo['Faixa de Idade'] = v; continue; }  // idade (etapa_02_homem/mulher)
    const m = k.match(/^etapa_\d+_(.+)$/i);
    if (m) { limpo[m[1].replace(/_/g, ' ')] = v; continue; }  // demais etapas: tira prefixo
    limpo[k] = v;
  }
  allFields = limpo;
}

// derivar Midia (Pago/Organico) a partir dos UTMs -> canal principal automatico
const _us = (byTitle['utm_source'] || '').toString().toLowerCase();
const _um = (byTitle['utm_medium'] || '').toString().toLowerCase();
const _uc = (byTitle['utm_campaign'] || '').toString().toLowerCase();
const _blob = _us + ' ' + _um + ' ' + _uc;
const _org = /organic|organ|bio|perfil|link.?bio|direct|whats/.test(_blob);
const midia = (_uc && !_org) ? 'Pago' : 'Organico';
allFields['Mídia'] = midia;
tags.push('midia-' + midia.toLowerCase());

// Origem do Lead (lista igual Talentus): prioridade anuncio > fonte do form
let origem_lead;
if (_uc && !_org) origem_lead = 'Trafego Pago';
else if (origem === 'site-wordpress') origem_lead = 'Pop-up Pagina';
else origem_lead = 'Organico';
allFields['Origem do Lead'] = origem_lead;

const basic = ['nome','name','seu nome','email','e-mail','whatsapp','telefone','celular','phone'];
const camposNovos = [];
for (const t of Object.keys(allFields)) {
  const tn = norm(t);
  if (basic.some(b => tn.includes(norm(b)))) continue;
  camposNovos.push(t);
}

let nivel = 'normal', motivo = '';
if (/<script|onerror=|javascript:|<iframe/i.test(JSON.stringify(body))) { nivel='bloqueio'; motivo='html injection'; }
const disp = ['mailinator','tempmail','guerrillamail','yopmail','10minutemail'];
if (email && disp.some(x => email.includes(x))) { nivel='bloqueio'; motivo='email descartavel'; }

const skip = nivel === 'bloqueio' || (!email && !telefone) || !nome;

return { json: {
  nome, email, telefone,
  formulario: formName || ('form-'+origem),
  origem, tags,
  _all_fields: allFields,
  _campos_novos: camposNovos,
  _skip: skip, _nivel: nivel, _motivo: motivo,
  data_cadastro: new Date().toISOString()
}};"""

MAPEAR = r"""// MAPEAR CAMPOS - match dos campos do form com os Custom Fields existentes do cliente.
// SEM PIT (listagem vem do node "Listar CFs" via credencial). Match-only; sem match -> _nao_mapeados.
const data = $('Extrair Campos').item.json;
const camposNovos = data._campos_novos || [];
const allFields = data._all_fields || {};
const existing = ($('Listar CFs').item.json.customFields) || [];

function norm(s){ return (s||'').toString().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^a-z0-9 ]+/g,' ').replace(/\s+/g,' ').trim(); }

function findMatch(t, list){
  const nn = norm(t); if (!nn) return null;
  for (const ef of list) if (norm(ef.name) === nn) return ef;
  if (nn.length >= 12) for (const ef of list){ const en = norm(ef.name); if (en.length >= 10 && (en.includes(nn) || nn.includes(en))) return ef; }
  const nt = nn.split(' ').filter(x => x.length > 3);
  for (const ef of list){ const et = norm(ef.name).split(' ').filter(x => x.length > 3); if (nt.filter(x => et.includes(x)).length >= 3) return ef; }
  return null;
}

const extra = [], logs = [], naoMapeados = [];
for (const t of camposNovos) {
  const val = allFields[t]; if (!val) continue;
  const m = findMatch(t, existing);
  if (m) { extra.push({ id: m.id, field_value: val }); logs.push('MATCH '+t.substring(0,40)+' -> '+m.name); }
  else { naoMapeados.push(t+': '+val); logs.push('SEM_MATCH '+t.substring(0,40)); }
}
return { json: Object.assign({}, data, { extra_custom_fields: extra, _nao_mapeados: naoMapeados, _cf_logs: logs }) };"""

LINHA_SHEETS = r"""// LINHA SHEETS - achata o lead em colunas universais (serve pra qualquer cliente)
const d = $('Mapear Campos').item.json;
return { json: {
  nome: d.nome || '',
  email: d.email || '',
  telefone: d.telefone || '',
  origem: d.origem || '',
  formulario: d.formulario || '',
  data_cadastro: d.data_cadastro || '',
  tags: (d.tags || []).join(', '),
  dados: JSON.stringify(d._all_fields || {})
}};"""

# linha no schema da planilha do cliente (ex: planilha da Julia) - cabecalhos exatos
LINHA_CLIENTE = r"""const d = $('Mapear Campos').item.json;
const al = d._all_fields || {};
function f(name){ for (const k of Object.keys(al)){ if (k.toLowerCase() === name.toLowerCase()) return al[k]; } return ''; }
return { json: {
  "Nome": d.nome || '',
  "Telefone": d.telefone || '',
  "Email": d.email || '',
  "GÊNERO": f('Gênero'),
  "IDADE": f('Faixa de Idade'),
  "JÁ FEZ ANTES?": f('Já fez harmonização antes'),
  "O QUE INCOMODA?": f('O que incomoda'),
  "SITUAÇÕES DESCONFORTÁVEIS": f('Situações desconfortáveis'),
  "FARIA?": f('Disposição (Faria)'),
  "Campanha": f('utm_campaign'),
  "Público": f('utm_term'),
  "Anúncio": f('utm_content'),
  "Termo": f('utm_medium'),
  "Fonte": f('utm_source'),
  "Origem": d.origem || '',
  "Data de cadastro": d.data_cadastro || ''
}};"""

# ---------------- node builders ----------------

CRED = {"httpHeaderAuth": {"id": "__CRED_ID__", "name": "__CRED_NAME__"}}


def code_node(name, code, x, y):
    return {"parameters": {"jsCode": code}, "id": name.lower().replace(" ", "-").replace("?", ""),
            "name": name, "type": "n8n-nodes-base.code", "typeVersion": V["code"], "position": [x, y]}


def webhook_node(name, path, x, y):
    return {"parameters": {"httpMethod": "POST", "path": path, "options": {}},
            "id": name.lower().replace(" ", "-"), "name": name,
            "type": "n8n-nodes-base.webhook", "typeVersion": V["webhook"], "position": [x, y]}


def if_node(name, left, op, x, y, right=""):
    return {"parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{"id": name + "-c", "leftValue": left, "rightValue": right, "operator": op}], "combinator": "and"}, "options": {}},
            "id": name.lower().replace(" ", "-").replace("?", ""), "name": name,
            "type": "n8n-nodes-base.if", "typeVersion": V["if"], "position": [x, y]}


def http_node(name, method, url, x, y, query=None, json_body=None):
    p = {"method": method, "url": url,
         "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
         "sendHeaders": True,
         "headerParameters": {"parameters": [{"name": "Version", "value": "2021-07-28"}]},
         "options": {"response": {"response": {"neverError": True}}}}
    if query:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": query}
    if json_body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = json_body
    return {"parameters": p, "id": name.lower().replace(" ", "-"), "name": name,
            "type": "n8n-nodes-base.httpRequest", "typeVersion": V["httpRequest"],
            "position": [x, y], "credentials": json.loads(json.dumps(CRED))}


def sheets_node(name, x, y, doc="__SHEET_ID__"):
    return {"parameters": {
        "operation": "append",
        "documentId": {"__rl": True, "mode": "id", "value": doc},
        "sheetName": {"__rl": True, "mode": "list", "value": "gid=0"},
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}},
        "id": name.lower().replace(" ", "-"), "name": name,
        "type": "n8n-nodes-base.googleSheets", "typeVersion": V["googleSheets"],
        "position": [x, y], "credentials": json.loads(json.dumps(GS_CRED)),
        # backup e best-effort: se o Sheets falhar nao quebra o fluxo nem alerta (GHL e o caminho critico)
        "onError": "continueRegularOutput"}


CRIAR_BODY = ("={{ JSON.stringify({ locationId: $('Config').item.json.location_id, "
              "firstName: $('Extrair Campos').item.json.nome, "
              "email: $('Extrair Campos').item.json.email || undefined, "
              "phone: $('Extrair Campos').item.json.telefone || undefined, "
              "source: $('Extrair Campos').item.json.formulario, "
              "tags: $('Extrair Campos').item.json.tags, "
              "customFields: ($('Mapear Campos').item.json.extra_custom_fields || []) }) }}")

ATUALIZAR_BODY = ("={{ JSON.stringify({ tags: $('Extrair Campos').item.json.tags, "
                  "customFields: ($('Mapear Campos').item.json.extra_custom_fields || []) }) }}")

EXISTS_OP = {"type": "string", "operation": "exists", "singleValue": True}
FALSE_OP = {"type": "boolean", "operation": "false", "singleValue": True}

nodes = [
    webhook_node("Webhook WordPress", "__SLUG__-wordpress", -760, -120),
    webhook_node("Webhook InLead", "__SLUG__-inlead", -760, 160),
    code_node("Origem WordPress", ORIGEM_WP, -540, -120),
    code_node("Origem InLead", ORIGEM_INLEAD, -540, 160),
    code_node("Config", CONFIG, -320, 0),
    code_node("Extrair Campos", EXTRAIR, -100, 0),
    if_node("Payload Valido?", "={{ $json._skip }}", FALSE_OP, 120, 0),
    http_node("Listar CFs", "GET", "=https://services.leadconnectorhq.com/locations/{{ $('Config').item.json.location_id }}/customFields", 340, 0),
    code_node("Mapear Campos", MAPEAR, 560, 0),
    http_node("Buscar Contato GHL", "GET", "https://services.leadconnectorhq.com/contacts/search/duplicate", 780, -40,
              query=[{"name": "locationId", "value": "={{ $('Config').item.json.location_id }}"},
                     {"name": "number", "value": "={{ $('Extrair Campos').item.json.telefone }}"},
                     {"name": "email", "value": "={{ $('Extrair Campos').item.json.email }}"}]),
    if_node("Contato Existe?", "={{ $json.contact?.id }}", EXISTS_OP, 1000, -40),
    http_node("Atualizar Contato", "PUT", "=https://services.leadconnectorhq.com/contacts/{{ $json.contact.id }}", 1220, -160, json_body=ATUALIZAR_BODY),
    http_node("Criar Contato", "POST", "https://services.leadconnectorhq.com/contacts/", 1220, 60, json_body=CRIAR_BODY),
    code_node("Linha Sheets", LINHA_SHEETS, 780, 220),
    sheets_node("Backup Sheets", 1000, 220),
    code_node("Linha Cliente", LINHA_CLIENTE, 780, 380),
    sheets_node("Backup Cliente", 1000, 380, "__SHEET_JULIA_ID__"),
]

connections = {
    "Webhook WordPress": {"main": [[{"node": "Origem WordPress", "type": "main", "index": 0}]]},
    "Webhook InLead": {"main": [[{"node": "Origem InLead", "type": "main", "index": 0}]]},
    "Origem WordPress": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
    "Origem InLead": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
    "Config": {"main": [[{"node": "Extrair Campos", "type": "main", "index": 0}]]},
    "Extrair Campos": {"main": [[{"node": "Payload Valido?", "type": "main", "index": 0}]]},
    "Payload Valido?": {"main": [[{"node": "Listar CFs", "type": "main", "index": 0}], []]},
    "Listar CFs": {"main": [[{"node": "Mapear Campos", "type": "main", "index": 0}]]},
    "Mapear Campos": {"main": [[{"node": "Buscar Contato GHL", "type": "main", "index": 0},
                               {"node": "Linha Sheets", "type": "main", "index": 0},
                               {"node": "Linha Cliente", "type": "main", "index": 0}]]},
    "Buscar Contato GHL": {"main": [[{"node": "Contato Existe?", "type": "main", "index": 0}]]},
    "Contato Existe?": {"main": [[{"node": "Atualizar Contato", "type": "main", "index": 0}], [{"node": "Criar Contato", "type": "main", "index": 0}]]},
    "Linha Sheets": {"main": [[{"node": "Backup Sheets", "type": "main", "index": 0}]]},
    "Linha Cliente": {"main": [[{"node": "Backup Cliente", "type": "main", "index": 0}]]},
}

wf = {"name": "__NOME_WF__", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1", "errorWorkflow": "__ERROR_WF_ID__"}}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template-workflow.json")
json.dump(wf, open(out, "w"), ensure_ascii=False, indent=2)
print("OK ->", out)
print("nodes:", len(nodes), "| typeVersions:", V)
