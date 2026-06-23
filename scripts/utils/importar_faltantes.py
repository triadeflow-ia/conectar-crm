#!/usr/bin/env python3
"""Importa pro CRM os leads da planilha do quiz que faltam, com telefone VALIDO.
Dry-run por padrao. --importar pra gravar.

Uso: python3 importar_faltantes.py <planilha.txt> <slug> [--importar]
"""
import json, os, re, subprocess, sys

PLAN, SLUG = sys.argv[1], sys.argv[2]
DO = "--importar" in sys.argv
c = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(os.path.expanduser(f"~/.secrets/clientes/{SLUG}.env"))
     if l.strip() and not l.startswith("#") and "=" in l)}
LOC, PIT = c["LOCATION_ID"], c["PIT"]
API = "https://services.leadconnectorhq.com"
DDDS = {11,12,13,14,15,16,17,18,19,21,22,24,27,28,31,32,33,34,35,37,38,41,42,43,44,45,46,47,48,49,
        51,53,54,55,61,62,63,64,65,66,67,68,69,71,73,74,75,77,79,81,82,83,84,85,86,87,88,89,
        91,92,93,94,95,96,97,98,99}


def norm(raw):
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    if len(d) == 10 and d[2] != "9":
        d = d[:2] + "9" + d[2:]
    return d


def valido(t):
    if len(t) != 11:
        return False
    if int(t[:2]) not in DDDS:
        return False
    if t[2] != "9":              # celular começa com 9
        return False
    if len(set(t[2:])) <= 2:     # 988888888 etc
        return False
    return True


def ghl(method, path, body=None):
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


# planilha
d = json.load(open(PLAN))
linhas = [l for l in d["fileContent"].split("\n") if l.strip().startswith("|")]
header = [h.strip() for h in linhas[0].strip("|").split("|")]
idx = {h: i for i, h in enumerate(header)}
iN, iT, iE = idx.get("Nome", 0), idx.get("Telefone", 2), idx.get("Email", 3)
plan = {}
for l in linhas[2:]:
    cells = [x.strip().replace("\\", "") for x in l.strip("|").split("|")]
    if len(cells) <= iT:
        continue
    t = norm(cells[iT]); nome = cells[iN] if len(cells) > iN else ""
    email = cells[iE] if len(cells) > iE else ""
    if t and nome.lower() not in ("nome", ""):
        plan[t] = {"nome": nome, "email": email}

# CRM telefones
crm = set(); url = f"/contacts/?locationId={LOC}&limit=100"
for _ in range(200):
    r = ghl("GET", url); cs = r.get("contacts", [])
    if not cs:
        break
    for ct in cs:
        x = norm(ct.get("phone", ""))
        if x:
            crm.add(x)
    m = r.get("meta", {})
    if not m.get("startAfterId"):
        break
    url = f"/contacts/?locationId={LOC}&limit=100&startAfterId={m['startAfterId']}&startAfter={m['startAfter']}"

faltam = {t: v for t, v in plan.items() if t not in crm}
val = {t: v for t, v in faltam.items() if valido(t)}
inval = {t: v for t, v in faltam.items() if not valido(t)}
print(f"faltantes: {len(faltam)} | telefone VALIDO: {len(val)} | INVALIDO (pular): {len(inval)}")
print("\nexemplos invalidos pulados:")
for t, v in list(inval.items())[:8]:
    print(f"   x {v['nome']} | +55{t}")

if not DO:
    print(f"\n[DRY-RUN] importaria {len(val)} contatos. Rode com --importar pra gravar.")
    sys.exit(0)

print(f"\n=== IMPORTANDO {len(val)} ===")
ok = fail = 0
for t, v in val.items():
    body = {"locationId": LOC, "firstName": v["nome"], "phone": "+55" + t,
            "tags": ["origem quiz instagram", "auditoria-faltante-22-06"]}
    em = (v.get("email") or "").strip()
    if em and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", em):
        body["email"] = em.lower()
    r = ghl("POST", "/contacts/upsert", body)
    if r.get("contact", {}).get("id"):
        ok += 1
    else:
        fail += 1
        if fail <= 5:
            print("  falhou:", v["nome"], str(r)[:120])
print(f"importados: {ok} | falhas: {fail}")
