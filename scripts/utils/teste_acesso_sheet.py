#!/usr/bin/env python3
"""Testa se a credencial Google do n8n consegue LER uma planilha (escopo).
Cria um workflow temp (webhook -> Sheets read), dispara, checa, deleta.
Uso: python3 teste_acesso_sheet.py <SPREADSHEET_ID>"""
import json, os, subprocess, sys, time

KV = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(os.path.expanduser("~/.secrets/n8n-triadeflow.env"))
      if l.strip() and not l.startswith("#") and "=" in l)}
BASE, KEY = KV["N8N_BASE_URL"], KV["N8N_API_KEY"]
GS = {"googleSheetsOAuth2Api": {"id": KV.get("GS_CRED_ID", ""), "name": KV.get("GS_CRED_NAME", "Google Sheets")}}
SHEET = sys.argv[1]


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
        return code, json.loads(raw or "{}", strict=False)
    except Exception:
        return code, {"raw": raw[:300]}


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "teste-acesso-sheet", "options": {}}, "id": "wh",
     "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2.1, "position": [0, 0]},
    {"parameters": {"operation": "read", "documentId": {"__rl": True, "mode": "id", "value": SHEET},
                    "sheetName": {"__rl": True, "mode": "list", "value": "gid=0"},
                    "options": {}}, "id": "rd", "name": "Ler", "type": "n8n-nodes-base.googleSheets",
     "typeVersion": 4.5, "position": [240, 0], "credentials": json.loads(json.dumps(GS))},
]
conns = {"Webhook": {"main": [[{"node": "Ler", "type": "main", "index": 0}]]}}
wf = {"name": "TESTE ACESSO SHEET (deletar)", "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}

st, res = api("POST", "/api/v1/workflows", wf)
wid = res.get("id")
if not wid:
    print("falhou criar:", st, str(res)[:200]); sys.exit(1)
api("POST", f"/api/v1/workflows/{wid}/activate")
subprocess.run(["curl", "-s", "-m", "30", "-X", "POST", "-A", "Mozilla/5.0",
                BASE.rstrip("/") + "/webhook/teste-acesso-sheet"], capture_output=True, text=True)
time.sleep(4)
_, ex = api("GET", f"/api/v1/executions?workflowId={wid}&limit=1")
exid = ex.get("data", [{}])[0].get("id")
_, det = api("GET", f"/api/v1/executions/{exid}?includeData=true")
run = det.get("data", {}).get("resultData", {}).get("runData", {})
node = (run.get("Ler") or [{}])[0]
if node.get("error"):
    print("RESULTADO: SEM ACESSO ->", node["error"].get("message"))
else:
    try:
        n = len(node["data"]["main"][0])
        print(f"RESULTADO: ACESSO OK -> leu {n} linha(s) da planilha")
    except Exception:
        print("RESULTADO: rodou sem erro (status", det.get("data", {}).get("resultData", {}).get("lastNodeExecuted"), ")")
# limpar
api("DELETE", f"/api/v1/workflows/{wid}")
print("(workflow de teste deletado)")
