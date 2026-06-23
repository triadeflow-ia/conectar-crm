#!/usr/bin/env python3
"""Auditoria: cruza os telefones da planilha do quiz com os contatos do CRM (GHL).
Reporta quem esta na planilha mas NAO no CRM (faltando importar).

Uso: python3 auditoria.py <arquivo_planilha.txt> <slug_cliente>
"""
import json, os, re, subprocess, sys

PLAN = sys.argv[1]
SLUG = sys.argv[2]
c = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(os.path.expanduser(f"~/.secrets/clientes/{SLUG}.env"))
     if l.strip() and not l.startswith("#") and "=" in l)}
LOC, PIT = c["LOCATION_ID"], c["PIT"]
API = "https://services.leadconnectorhq.com"


def norm_tel(raw):
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    if len(d) == 10 and d[2] != "9":
        d = d[:2] + "9" + d[2:]
    return d if len(d) >= 10 else ""


def ghl(path):
    out = subprocess.run(["curl", "-s", "-m", "30", "-A", "Mozilla/5.0",
                          "-H", f"Authorization: Bearer {PIT}", "-H", "Version: 2021-07-28", API + path],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out or "{}", strict=False)
    except Exception:
        return {}


# 1) planilha -> {tel: nome}
d = json.load(open(PLAN))
linhas = [l for l in d["fileContent"].split("\n") if l.strip().startswith("|")]
header = [h.strip() for h in linhas[0].strip("|").split("|")]
idx = {h: i for i, h in enumerate(header)}
iNome, iTel = idx.get("Nome", 0), idx.get("Telefone", 2)
plan = {}
for l in linhas[2:]:
    cells = [x.strip().replace("\\", "") for x in l.strip("|").split("|")]
    if len(cells) <= iTel:
        continue
    t = norm_tel(cells[iTel])
    nome = cells[iNome] if len(cells) > iNome else ""
    if t and nome.lower() not in ("nome", ""):
        plan[t] = nome
print("leads na planilha (com telefone valido):", len(plan))

# 2) CRM -> set de telefones
crm = set()
total = 0
url = f"/contacts/?locationId={LOC}&limit=100"
for _ in range(200):  # ate 20k contatos
    r = ghl(url)
    cs = r.get("contacts", [])
    if not cs:
        break
    total += len(cs)
    for ct in cs:
        t = norm_tel(ct.get("phone", ""))
        if t:
            crm.add(t)
    meta = r.get("meta", {})
    saId, sa = meta.get("startAfterId"), meta.get("startAfter")
    if not saId or not r.get("contacts"):
        break
    url = f"/contacts/?locationId={LOC}&limit=100&startAfterId={saId}&startAfter={sa}"
print("contatos no CRM:", total, "| com telefone:", len(crm))

# 3) diff
faltam = {t: n for t, n in plan.items() if t not in crm}
print("\n=== RESULTADO ===")
print("na planilha e JA no CRM:", len(plan) - len(faltam))
print("na planilha e FALTANDO no CRM:", len(faltam))
if faltam:
    print("\n-- faltantes (ate 40) --")
    for t, n in list(faltam.items())[:40]:
        print(f"   {n}  | +55{t}")
    # salvar lista completa
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"faltantes_{SLUG}.json")
    json.dump([{"nome": n, "telefone": "+55" + t} for t, n in faltam.items()], open(out, "w"), ensure_ascii=False, indent=2)
    print(f"\nlista completa salva em {out}")
