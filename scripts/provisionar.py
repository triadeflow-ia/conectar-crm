#!/usr/bin/env python3
"""
Provisiona um cliente no motor "Form -> GHL" do n8n. NUCLEO da skill conectar-crm.

Passos:
  1. cria CREDENCIAL httpHeaderAuth no n8n (Authorization: Bearer <PIT>) -> PIT criptografado
  2. clona o template-workflow.json (injeta cred id + location + slug + nome)
  3. cria o workflow (INATIVO; ativar so apos auditoria NO MASS DISPATCH)

O PIT NUNCA vem por argumento de linha de comando. Vem de um arquivo de secrets do
cliente: ~/.secrets/clientes/<slug>.env  com:
    LOCATION_ID=...
    PIT=...

Uso:
  python3 provisionar.py --slug gabriely --cliente "Gabriely de Boulos" [--ativar]
"""
import argparse, json, os, sys, subprocess

# multi-ambiente: define CONECTAR_CRM_ENV pra apontar pro env do n8n desejado
N8N_SECRETS = os.path.expanduser(os.environ.get("CONECTAR_CRM_ENV") or "~/.secrets/n8n-triadeflow.env")
CLIENT_SECRETS_DIR = os.path.expanduser("~/.secrets/clientes")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template-workflow.json")


def load_kv(path):
    kv = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def api(base, key, method, path, body=None):
    # usa curl (CA do sistema) e passa o body por stdin (segredo nunca em argv)
    url = base.rstrip("/") + path
    cmd = ["curl", "-s", "-m", "30", "-X", method, "-A", "Mozilla/5.0",
           "-H", f"X-N8N-API-KEY: {key}", "-H", "Content-Type: application/json",
           "-w", "\n__HTTP__%{http_code}"]
    stdin = None
    if body is not None:
        cmd += ["--data-binary", "@-"]
        stdin = json.dumps(body)
    cmd.append(url)
    out = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    raw, code = out.stdout, 0
    if "__HTTP__" in raw:
        raw, c = raw.rsplit("__HTTP__", 1)
        code = int(c.strip() or 0)
    try:
        return code, json.loads(raw or "{}")
    except Exception:
        return code, {"raw": raw[:400]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--cliente", required=True)
    ap.add_argument("--nome", default=None)
    ap.add_argument("--ativar", action="store_true", help="ativa o workflow (so apos auditar no-mass-dispatch)")
    a = ap.parse_args()

    n8n = load_kv(N8N_SECRETS)
    base, key = n8n["N8N_BASE_URL"], n8n["N8N_API_KEY"]
    error_wf_id = n8n.get("ERROR_WF_ID", "")
    gs_cred_id = n8n.get("GS_CRED_ID", "")
    gs_cred_name = n8n.get("GS_CRED_NAME", "Google Sheets")

    csec = os.path.join(CLIENT_SECRETS_DIR, f"{a.slug}.env")
    if not os.path.exists(csec):
        print(f"FALTA secrets do cliente: {csec}\n  crie com LOCATION_ID=... PIT=... SHEET_ID=..."); sys.exit(1)
    c = load_kv(csec)
    location, pit = c["LOCATION_ID"], c["PIT"]
    sheet_id = c.get("SHEET_ID", "")
    sheet_julia_id = c.get("SHEET_JULIA_ID", "")

    nome_wf = a.nome or f"Form->GHL | {a.cliente}"
    cred_name = f"GHL PIT | {a.cliente}"

    # 1) credencial (PIT criptografado no n8n)
    st, res = api(base, key, "POST", "/api/v1/credentials",
                  {"name": cred_name, "type": "httpHeaderAuth",
                   "data": {"name": "Authorization", "value": "Bearer " + pit}})
    if st not in (200, 201) or not res.get("id"):
        print("FALHOU criar credencial:", st, str(res)[:400]); sys.exit(1)
    cred_id = res["id"]
    print(f"credencial criada: {cred_id}  ({cred_name})")

    # 2) clona template
    tpl = open(TEMPLATE).read()
    tpl = (tpl.replace("__LOCATION_ID__", location)
              .replace("__CLIENTE__", a.cliente)
              .replace("__SLUG__", a.slug)
              .replace("__NOME_WF__", nome_wf)
              .replace("__CRED_ID__", cred_id)
              .replace("__CRED_NAME__", cred_name)
              .replace("__SHEET_ID__", sheet_id)
              .replace("__ERROR_WF_ID__", error_wf_id)
              .replace("__GS_CRED_ID__", gs_cred_id)
              .replace("__GS_CRED_NAME__", gs_cred_name)
              .replace("__SHEET_JULIA_ID__", sheet_julia_id))
    wf = json.loads(tpl)
    # sem error workflow configurado -> nao setar (n8n rejeita id vazio)
    if not error_wf_id:
        wf.get("settings", {}).pop("errorWorkflow", None)
    # remove ramos de Sheets sem credencial/destino (GHL sempre funciona)
    def _drop_branch(linha, backup):
        wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in (linha, backup)]
        wf["connections"].pop(linha, None)
        mc = wf["connections"].get("Mapear Campos", {}).get("main", [[]])
        if mc and mc[0]:
            mc[0][:] = [x for x in mc[0] if x["node"] != linha]
    if not gs_cred_id:
        _drop_branch("Linha Sheets", "Backup Sheets")
        _drop_branch("Linha Cliente", "Backup Cliente")
    else:
        if not sheet_id:
            _drop_branch("Linha Sheets", "Backup Sheets")
        if not sheet_julia_id:
            _drop_branch("Linha Cliente", "Backup Cliente")

    # 3) cria workflow
    st, res = api(base, key, "POST", "/api/v1/workflows", wf)
    if st not in (200, 201) or not res.get("id"):
        print("FALHOU criar workflow:", st, str(res)[:400]); sys.exit(1)
    wid = res["id"]
    print(f"workflow criado: {wid}  ({nome_wf})")

    if a.ativar:
        st2, _ = api(base, key, "POST", f"/api/v1/workflows/{wid}/activate")
        print("ativacao ->", "OK" if st2 in (200, 201) else f"FALHOU ({st2})")
    else:
        print("workflow INATIVO (rode --ativar so apos auditar NO MASS DISPATCH)")

    print("\nURLs dos webhooks (colar na fonte):")
    print("  WordPress :", f"{base.rstrip('/')}/webhook/{a.slug}-wordpress")
    print("  InLead    :", f"{base.rstrip('/')}/webhook/{a.slug}-inlead")
    print("  (teste use /webhook-test/ no lugar de /webhook/)")


if __name__ == "__main__":
    main()
