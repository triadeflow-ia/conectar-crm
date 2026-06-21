#!/usr/bin/env python3
"""
Utilitario reusavel: cria um workflow n8n "Util - Criar Planilha Backup" que, via webhook,
cria uma planilha Google PELA credencial MAU (escopo drive.file -> a MAU passa a ter acesso).
A skill chama esse webhook por cliente pra gerar a planilha de backup.

Uso:
  python3 build_criar_planilha.py            # cria/ativa o workflow util (1 vez)
  python3 build_criar_planilha.py "<nome>"   # chama o util e cria a planilha, imprime o ID
"""
import json, os, sys, subprocess

N8N_SECRETS = os.path.expanduser("~/.secrets/n8n-triadeflow.env")
PATH = "util-criar-planilha"
WF_NAME = "Util - Criar Planilha Backup"

_KV = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(N8N_SECRETS)
       if l.strip() and not l.startswith("#") and "=" in l)}
GS_CRED = {"googleSheetsOAuth2Api": {"id": _KV.get("GS_CRED_ID", ""), "name": _KV.get("GS_CRED_NAME", "Google Sheets")}}


def env():
    return _KV["N8N_BASE_URL"], _KV["N8N_API_KEY"]


def api(base, key, method, path, body=None):
    cmd = ["curl", "-s", "-m", "40", "-X", method, "-A", "Mozilla/5.0",
           "-H", f"X-N8N-API-KEY: {key}", "-H", "Content-Type: application/json", "-w", "\n__H__%{http_code}"]
    stdin = None
    if body is not None:
        cmd += ["--data-binary", "@-"]; stdin = json.dumps(body)
    cmd.append(base.rstrip("/") + path)
    out = subprocess.run(cmd, input=stdin, capture_output=True, text=True).stdout
    raw, code = out, 0
    if "__H__" in raw:
        raw, c = raw.rsplit("__H__", 1); code = int(c.strip() or 0)
    try:
        return code, json.loads(raw or "{}")
    except Exception:
        return code, {"raw": raw[:300]}


def build_wf():
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": PATH, "responseMode": "lastNode", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2.1, "position": [0, 0]},
        {"parameters": {"resource": "spreadsheet", "operation": "create",
                        "title": "={{ $json.body.nome }}", "options": {}},
         "id": "gs", "name": "Criar Planilha", "type": "n8n-nodes-base.googleSheets",
         "typeVersion": 4.5, "position": [240, 0], "credentials": json.loads(json.dumps(GS_CRED))},
    ]
    conns = {"Webhook": {"main": [[{"node": "Criar Planilha", "type": "main", "index": 0}]]}}
    return {"name": WF_NAME, "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}


def main():
    base, key = env()
    if len(sys.argv) > 1:
        nome = sys.argv[1]
        st, res = api(base, key, "POST", "/webhook/" + PATH, {"nome": nome})
        # resposta pode ser o objeto do node Sheets
        sid = (res.get("spreadsheetId") or res.get("id")
               or (res.get("spreadsheetUrl") or "").split("/d/")[-1].split("/")[0])
        print("HTTP", st, "| resposta:", json.dumps(res)[:300])
        if sid:
            print("SHEET_ID=" + sid)
        return
    # criar o workflow util
    st, res = api(base, key, "POST", "/api/v1/workflows", build_wf())
    if not res.get("id"):
        print("FALHOU:", st, str(res)[:300]); sys.exit(1)
    wid = res["id"]
    api(base, key, "POST", f"/api/v1/workflows/{wid}/activate")
    print("util criado e ativo:", wid, "| webhook:", base.rstrip("/") + "/webhook/" + PATH)


if __name__ == "__main__":
    main()
