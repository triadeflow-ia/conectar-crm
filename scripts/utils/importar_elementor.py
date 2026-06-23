#!/usr/bin/env python3
"""Importa pro CRM os envios exportados do Elementor (zip com CSVs), com telefone valido.
Dry-run por padrao. --importar pra gravar.

Uso: python3 importar_elementor.py <export.zip> <slug> [--importar]
"""
import zipfile, csv, io, os, re, subprocess, sys

ZIP, SLUG = sys.argv[1], sys.argv[2]
DO = "--importar" in sys.argv
c = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(os.path.expanduser(f"~/.secrets/clientes/{SLUG}.env"))
     if l.strip() and not l.startswith("#") and "=" in l)}
LOC, PIT = c["LOCATION_ID"], c["PIT"]
API = "https://services.leadconnectorhq.com"
DDDS = {11,12,13,14,15,16,17,18,19,21,22,24,27,28,31,32,33,34,35,37,38,41,42,43,44,45,46,47,48,49,
        51,53,54,55,61,62,63,64,65,66,67,68,69,71,73,74,75,77,79,81,82,83,84,85,86,87,88,89,91,92,93,94,95,96,97,98,99}


def norm(raw):
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    if len(d) == 10 and d[2] != "9":
        d = d[:2] + "9" + d[2:]
    return d


def valido(t):
    return len(t) == 11 and int(t[:2]) in DDDS and t[2] == "9" and len(set(t[2:])) > 2


def nome_teste(n):
    nl = (n or "").lower().strip()
    return (nl in ("teste", "test") or nl.startswith("teste ") or nl.startswith("test ")
            or "web design" in nl or nl.replace(" ", "").isdigit())


def ghl(method, path, body=None):
    cmd = ["curl", "-s", "-m", "30", "-X", method, "-A", "Mozilla/5.0",
           "-H", f"Authorization: Bearer {PIT}", "-H", "Version: 2021-07-28"]
    stdin = None
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", "@-"]; stdin = json.dumps(body)
    cmd.append(API + path)
    out = subprocess.run(cmd, input=stdin, capture_output=True, text=True).stdout
    try:
        import json as _j; return _j.loads(out or "{}", strict=False)
    except Exception:
        return {"raw": out[:200]}


import json
# 1) ler envios do zip
leads = {}
z = zipfile.ZipFile(os.path.expanduser(ZIP))
for n in z.namelist():
    if not n.lower().endswith(".csv"):
        continue
    r = csv.DictReader(io.StringIO(z.read(n).decode("utf-8", errors="replace")))
    for row in r:
        nome = (row.get("Nome e Sobrenome") or "").strip()
        tel = norm(row.get("Qual o WhatsApp?") or row.get("phone") or "")
        form = row.get("Form Name (ID)") or ""
        igmail = (row.get("Qual seu  instagram profissional?") or "").strip()
        email = igmail.lower() if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", igmail) else ""
        tag = "origem mentoria alem do full face" if "7329af0d" in form else "origem popup metodo fullface"
        if tel and nome:
            leads[tel] = {"nome": nome, "email": email, "tag": tag}
print("envios com nome+telefone:", len(leads))

# 2) CRM telefones
crm = set(); url = f"/contacts/?locationId={LOC}&limit=100"
for _ in range(200):
    rr = ghl("GET", url); cs = rr.get("contacts", [])
    if not cs:
        break
    for ct in cs:
        x = norm(ct.get("phone", ""))
        if x:
            crm.add(x)
    m = rr.get("meta", {})
    if not m.get("startAfterId"):
        break
    url = f"/contacts/?locationId={LOC}&limit=100&startAfterId={m['startAfterId']}&startAfter={m['startAfter']}"

faltam = {t: v for t, v in leads.items() if t not in crm}
val = {t: v for t, v in faltam.items() if valido(t) and not nome_teste(v["nome"])}
inval = {t: v for t, v in faltam.items() if not (valido(t) and not nome_teste(v["nome"]))}
print(f"ja no CRM: {len(leads)-len(faltam)} | faltando: {len(faltam)} | validos: {len(val)} | invalidos(pular): {len(inval)}")
print("\nvalidos a importar:")
for t, v in val.items():
    print(f"   {v['nome']} | +55{t} | [{v['tag']}]")
if inval:
    print("\ninvalidos pulados:")
    for t, v in inval.items():
        print(f"   x {v['nome']} | +55{t}")

if not DO:
    print(f"\n[DRY-RUN] importaria {len(val)}. Rode com --importar.")
    sys.exit(0)

print(f"\n=== IMPORTANDO {len(val)} ===")
ok = fail = 0
for t, v in val.items():
    body = {"locationId": LOC, "firstName": v["nome"], "phone": "+55" + t,
            "tags": [v["tag"], "elementor-import-23-06"]}
    if v["email"]:
        body["email"] = v["email"]
    r = ghl("POST", "/contacts/upsert", body)
    if r.get("contact", {}).get("id"):
        ok += 1
    else:
        fail += 1
        if fail <= 5:
            print("  falhou:", v["nome"], str(r)[:120])
print(f"importados: {ok} | falhas: {fail}")
