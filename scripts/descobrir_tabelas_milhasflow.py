#!/usr/bin/env python3
"""Lista as tabelas e colunas que o MilhasFlow expoe via PostgREST.

Serve pra descobrir onde ficam as contas cadastradas (cedentes) e com que
nome cada coluna aparece la — o schema e deles, entao chutar nome de campo
no codigo viraria bug que so aparece na hora de aprovar um cedente.

Roda na SUA maquina, com o .env do projeto ja preenchido:

    python3 scripts/descobrir_tabelas_milhasflow.py            # so os nomes
    python3 scripts/descobrir_tabelas_milhasflow.py cedente    # filtra
    python3 scripts/descobrir_tabelas_milhasflow.py --colunas cedentes

Precisa apenas de MILHASFLOW_ANON_KEY: a chave anon e publica (fica no
proprio site do MilhasFlow), e o /rest/v1/ devolve o OpenAPI do schema sem
login. O que exige login e escrever — isso quem testa e o site, na hora de
aprovar.
"""

import json
import os
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL_PADRAO = "https://SEU_PROJETO_MILHASFLOW.supabase.co"


def carregar_env():
    """Le o .env da raiz sem depender de biblioteca externa."""
    caminho = os.path.join(RAIZ, ".env")
    if not os.path.exists(caminho):
        return
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


def buscar_esquema(base, anon_key):
    req = urllib.request.Request(
        base.rstrip("/") + "/rest/v1/",
        headers={"apikey": anon_key, "Accept": "application/openapi+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:300]
        sys.exit("HTTP %s ao ler o schema:\n%s" % (e.code, detalhe))
    except urllib.error.URLError as e:
        sys.exit("Falha de conexao: %s" % e.reason)


def main():
    carregar_env()

    anon_key = os.environ.get("MILHASFLOW_ANON_KEY")
    if not anon_key:
        sys.exit(
            "MILHASFLOW_ANON_KEY nao esta no .env.\n"
            "Como pegar: abra o MilhasFlow logado no Chrome, F12 > Network,\n"
            "recarregue, clique numa linha 'supabase.co' e copie o header 'apikey'."
        )

    base = os.environ.get("MILHASFLOW_URL") or os.environ.get("SUPABASE_URL") or URL_PADRAO

    args = [a for a in sys.argv[1:]]
    detalhar = "--colunas" in args
    if detalhar:
        args.remove("--colunas")
    filtro = (args[0].lower() if args else "")

    esquema = buscar_esquema(base, anon_key)
    definicoes = esquema.get("definitions", {})

    encontradas = sorted(t for t in definicoes if filtro in t.lower())
    if not encontradas:
        print("Nenhuma tabela com '%s' no nome." % filtro)
        return

    for tabela in encontradas:
        print(tabela)
        if detalhar:
            props = definicoes[tabela].get("properties", {})
            for coluna in sorted(props):
                info = props[coluna]
                tipo = info.get("format") or info.get("type") or "?"
                print("    %-32s %s" % (coluna, tipo))
            print()

    if not detalhar:
        print("\n%d tabela(s). Use --colunas <tabela> pra ver os campos." % len(encontradas))


if __name__ == "__main__":
    main()
