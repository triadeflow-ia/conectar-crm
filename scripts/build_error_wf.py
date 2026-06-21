#!/usr/bin/env python3
"""
Cria o ERROR WORKFLOW GLOBAL do n8n: qualquer motor Form->GHL que falhar dispara alerta.
Canais lidos do env ~/.secrets/n8n-triadeflow.env:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID            (obrigatorio)
  EVOLUTION_URL, EVOLUTION_APIKEY, ALERT_WHATSAPP (opcional - WhatsApp via Evolution)

Cada workflow de cliente aponta pra ele via settings.errorWorkflow.
Apos criar, salve o ID retornado como ERROR_WF_ID no mesmo env.

Uso: python3 build_error_wf.py
"""
import json, os, subprocess, sys

N8N_SECRETS = os.path.expanduser("~/.secrets/n8n-triadeflow.env")
KV = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(N8N_SECRETS)
      if l.strip() and not l.startswith("#") and "=" in l)}
BASE, KEY = KV["N8N_BASE_URL"], KV["N8N_API_KEY"]
TG_TOKEN = KV.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = KV.get("TELEGRAM_CHAT_ID", "")
EVO_URL = KV.get("EVOLUTION_URL", "")
EVO_KEY = KV.get("EVOLUTION_APIKEY", "")
ALERT_WA = KV.get("ALERT_WHATSAPP", "")


def api(method, path, body=None):
    cmd = ["curl", "-s", "-m", "30", "-X", method, "-A", "Mozilla/5.0",
           "-H", f"X-N8N-API-KEY: {KEY}", "-H", "Content-Type: application/json", "-w", "\n__H__%{http_code}"]
    stdin = None
    if body is not None:
        cmd += ["--data-binary", "@-"]; stdin = json.dumps(body)
    cmd.append(BASE.rstrip("/") + path)
    out = subprocess.run(cmd, input=stdin, capture_output=True, text=True).stdout
    raw, code = out, 0
    if "__H__" in raw:
        raw, c = raw.rsplit("__H__", 1); code = int(c.strip() or 0)
    try:
        return code, json.loads(raw or "{}")
    except Exception:
        return code, {"raw": raw[:300]}


if not TG_TOKEN or not TG_CHAT:
    print("FALTA TELEGRAM_BOT_TOKEN e/ou TELEGRAM_CHAT_ID no", N8N_SECRETS)
    print("(crie um bot no @BotFather, pegue o token; descubra seu chat_id no @userinfobot)")
    sys.exit(1)

MONTAR = (
    "const e = $json || {};\n"
    "const wf = (e.workflow||{}).name || '?';\n"
    "const node = (e.execution||{}).lastNodeExecuted || '?';\n"
    "const msg = (((e.execution||{}).error)||{}).message || 'sem mensagem';\n"
    "const url = (e.execution||{}).url || '';\n"
    "const text = '\\u26a0\\ufe0f ERRO motor Form->GHL\\n\\nWorkflow: ' + wf + '\\nNode: ' + node + '\\nErro: ' + msg + (url ? ('\\nExec: ' + url) : '');\n"
    f"return {{ json: {{ chat_id: '{TG_CHAT}', number: '{ALERT_WA}', text }} }};"
)

nodes = [
    {"parameters": {}, "id": "error-trigger", "name": "Error Trigger",
     "type": "n8n-nodes-base.errorTrigger", "typeVersion": 1, "position": [-300, 0]},
    {"parameters": {"jsCode": MONTAR}, "id": "montar-alerta", "name": "Montar Alerta",
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-80, 0]},
    {"parameters": {"method": "POST", "url": f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    "sendBody": True, "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify({ chat_id: $json.chat_id, text: $json.text }) }}",
                    "options": {"response": {"response": {"neverError": True}}}},
     "id": "tg", "name": "Telegram Alerta", "type": "n8n-nodes-base.httpRequest",
     "typeVersion": 4.2, "position": [160, -100]},
]
conns = {"Error Trigger": {"main": [[{"node": "Montar Alerta", "type": "main", "index": 0}]]},
         "Montar Alerta": {"main": [[{"node": "Telegram Alerta", "type": "main", "index": 0}]]}}

# WhatsApp opcional (Evolution)
if EVO_URL and EVO_KEY and ALERT_WA:
    nodes.append({"parameters": {"method": "POST", "url": EVO_URL, "sendHeaders": True,
                  "headerParameters": {"parameters": [{"name": "apikey", "value": EVO_KEY}]},
                  "sendBody": True, "specifyBody": "json",
                  "jsonBody": "={{ JSON.stringify({ number: $json.number, text: $json.text }) }}",
                  "options": {"response": {"response": {"neverError": True}}}},
                  "id": "wa", "name": "WhatsApp Alerta", "type": "n8n-nodes-base.httpRequest",
                  "typeVersion": 4.2, "position": [160, 100]})
    conns["Montar Alerta"]["main"][0].append({"node": "WhatsApp Alerta", "type": "main", "index": 0})

wf = {"name": "ERRO GLOBAL - Motores Form->GHL", "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1"}}

st, res = api("POST", "/api/v1/workflows", wf)
if st not in (200, 201) or not res.get("id"):
    print("FALHOU:", st, str(res)[:400]); sys.exit(1)
wid = res["id"]
api("POST", f"/api/v1/workflows/{wid}/activate")
print("error workflow criado e ativo:", wid)
print(">>> salve no", N8N_SECRETS, ": ERROR_WF_ID=" + wid)
