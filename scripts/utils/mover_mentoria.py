#!/usr/bin/env python3
"""Move as oportunidades dos leads de MENTORIA (tag) do pipeline Comercial -> Mentoria.
Dry-run por padrao. --mover pra aplicar.

Uso: python3 mover_mentoria.py <slug> [--mover]
"""
import json, os, subprocess, sys

SLUG = sys.argv[1]
DO = "--mover" in sys.argv
c = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(os.path.expanduser(f"~/.secrets/clientes/{SLUG}.env"))
     if l.strip() and not l.startswith("#") and "=" in l)}
LOC, PIT = c["LOCATION_ID"], c["PIT"]
API = "https://services.leadconnectorhq.com"
TAGS_MENTORIA = ["metodo-fullface", "mentoria alem", "popup metodo"]


def gh(method, path, body=None):
    cmd = ["curl", "-s", "-m", "30", "-X", method, "-A", "Mozilla/5.0",
           "-H", f"Authorization: Bearer {PIT}", "-H", "Version: 2021-07-28"]
    stdin = None
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", "@-"]; stdin = json.dumps(body)
    cmd.append(API + path)
    out = subprocess.run(cmd, input=stdin, capture_output=True, text=True).stdout
    try:
        return json.loads(out or "{}", strict=False)
    except Exception:
        return {"raw": out[:200]}


def is_mentoria(tags):
    t = " | ".join(tags or []).lower()
    return any(k in t for k in TAGS_MENTORIA)


# pipelines
pipes = gh("GET", f"/opportunities/pipelines?locationId={LOC}").get("pipelines", [])
comercial = next((p for p in pipes if p["name"].lower() == "comercial"), None)
mentoria = next((p for p in pipes if p["name"].lower() == "mentoria"), None)
if not mentoria or not comercial:
    print("FALTA pipeline Comercial/Mentoria:", [p["name"] for p in pipes]); sys.exit(1)
ment_stage = mentoria["stages"][0]["id"]
ment_stage_nome = mentoria["stages"][0]["name"]
com_id = comercial["id"]
print(f"Comercial id={com_id} | Mentoria id={mentoria['id']} stage1='{ment_stage_nome}'")

# contatos com tag de mentoria
ment_contacts = {}
url = f"/contacts/?locationId={LOC}&limit=100"
for _ in range(200):
    r = gh("GET", url); cs = r.get("contacts", [])
    if not cs:
        break
    for ct in cs:
        if is_mentoria(ct.get("tags", [])):
            ment_contacts[ct["id"]] = ct.get("contactName") or ct.get("firstName") or "?"
    m = r.get("meta", {})
    if not m.get("startAfterId"):
        break
    url = f"/contacts/?locationId={LOC}&limit=100&startAfterId={m['startAfterId']}&startAfter={m['startAfter']}"
print("contatos com tag de mentoria:", len(ment_contacts))

# oportunidades no Comercial desses contatos -> mover
mover = []
for cid, nome in ment_contacts.items():
    o = gh("GET", f"/opportunities/search?location_id={LOC}&contact_id={cid}")
    for op in o.get("opportunities", []):
        if op.get("pipelineId") == com_id:
            mover.append((op["id"], nome))
print(f"oportunidades no Comercial pra mover -> Mentoria: {len(mover)}")
for opid, nome in mover[:30]:
    print("   ", nome)

if not DO:
    print(f"\n[DRY-RUN] moveria {len(mover)} oportunidades. Rode com --mover.")
    sys.exit(0)

print(f"\n=== MOVENDO {len(mover)} ===")
ok = fail = 0
for opid, nome in mover:
    r = gh("PUT", f"/opportunities/{opid}", {"pipelineId": mentoria["id"], "pipelineStageId": ment_stage})
    if r.get("opportunity", {}).get("id") or r.get("succeded") or r.get("succeeded"):
        ok += 1
    else:
        fail += 1
        if fail <= 5:
            print("  falhou:", nome, str(r)[:120])
print(f"movidas: {ok} | falhas: {fail}")
