#!/usr/bin/env python3
"""Cria os custom fields de RASTREAMENTO padrao na conta GHL do cliente (idempotente).
Le LOCATION_ID + PIT de ~/.secrets/clientes/<slug>.env

Campos: utm_source/medium/campaign/content/term (TEXT), Mídia (TEXT),
        Origem do Lead (SINGLE_OPTIONS, 8 opcoes igual Talentus).

Uso: python3 setup_rastreamento.py --slug <slug>
"""
import argparse, json, os, subprocess, sys

API = "https://services.leadconnectorhq.com"
ORIGEM_OPCOES = ["Indicacao", "Trafego Pago", "Organico", "Social Selling",
                 "Evento", "Parceiro", "Pop-up Pagina", "ManyChat"]
CAMPOS = [("utm_source", "TEXT"), ("utm_medium", "TEXT"), ("utm_campaign", "TEXT"),
          ("utm_content", "TEXT"), ("utm_term", "TEXT"), ("Mídia", "TEXT"),
          ("Origem do Lead", "SINGLE_OPTIONS")]


def kv(path):
    return {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in open(path)
            if l.strip() and not l.startswith("#") and "=" in l)}


def ghl(pit, method, path, body=None):
    cmd = ["curl", "-s", "-m", "25", "-X", method, "-A", "Mozilla/5.0",
           "-H", f"Authorization: Bearer {pit}", "-H", "Version: 2021-07-28",
           "-H", "Content-Type: application/json"]
    stdin = None
    if body is not None:
        cmd += ["--data-binary", "@-"]; stdin = json.dumps(body)
    cmd.append(API + path)
    out = subprocess.run(cmd, input=stdin, capture_output=True, text=True).stdout
    try:
        return json.loads(out or "{}")
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--slug", required=True)
    slug = ap.parse_args().slug
    c = kv(os.path.expanduser(f"~/.secrets/clientes/{slug}.env"))
    loc, pit = c["LOCATION_ID"], c["PIT"]

    existing = {f["name"].lower(): f for f in ghl(pit, "GET", f"/locations/{loc}/customFields").get("customFields", [])}
    for nome, dt in CAMPOS:
        if nome.lower() in existing:
            print(f"  = {nome} (ja existe)"); continue
        body = {"name": nome, "dataType": dt}
        if dt == "SINGLE_OPTIONS":
            body["options"] = ORIGEM_OPCOES
        r = ghl(pit, "POST", f"/locations/{loc}/customFields", body).get("customField", {})
        print(f"  + {nome} -> {r.get('id', 'FALHOU')}")
    print("rastreamento ok.")


if __name__ == "__main__":
    main()
