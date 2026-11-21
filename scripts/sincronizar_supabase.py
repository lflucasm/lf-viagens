"""Sincroniza voos/historico/observacoes do voos.db pro Supabase do painel
web, na mão (fora da rotina automática do bot).

A rotina automática já chama isso sozinha no fim de rodada.py e
checar_malha.py (ver src/sincronizar_web.py) — este script serve pra
sincronizar sob demanda, ou apontar pra um banco diferente do padrão do
.env (ex: testar contra o Supabase local antes de configurar o hospedado).

Uso:
  SUPABASE_SERVICE_ROLE_KEY=<chave> python3 scripts/sincronizar_supabase.py \
      --banco /caminho/pro/voos.db [--supabase-url URL]
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import sincronizar_web

PADRAO_SUPABASE_URL = "http://127.0.0.1:54321"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--banco", required=True, help="caminho do voos.db (SQLite) a espelhar")
    ap.add_argument("--supabase-url", default=PADRAO_SUPABASE_URL)
    args = ap.parse_args()

    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise SystemExit("Defina SUPABASE_SERVICE_ROLE_KEY no ambiente antes de rodar.")
    if not os.path.exists(args.banco):
        raise SystemExit("Banco nao encontrado: %s" % args.banco)

    con = sqlite3.connect(args.banco)
    ok, msg = sincronizar_web.sincronizar(con, args.supabase_url, service_key)
    con.close()

    if not ok:
        raise SystemExit("Falha na sincronizacao: %s" % msg)
    print("Sincronizado: %s" % msg)


if __name__ == "__main__":
    main()
