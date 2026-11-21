"""Relatório: quais voos (já importados no Supabase) dá pra checar automático
e quais precisam de atenção manual — reaproveita src/qualidade.py, a mesma
regra que o bot já usa pra decidir isso.

Uso:
  SUPABASE_SERVICE_ROLE_KEY=<chave> python3 scripts/relatorio_checabilidade.py
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import qualidade

PADRAO_SUPABASE_URL = "http://127.0.0.1:54321"


def buscar_voos(supabase_url, service_key):
    req = urllib.request.Request(
        supabase_url.rstrip("/") + "/rest/v1/voos?select=*&ativo=eq.true&order=embarque.asc",
        headers={"apikey": service_key, "Authorization": "Bearer " + service_key},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise SystemExit("Defina SUPABASE_SERVICE_ROLE_KEY no ambiente antes de rodar.")
    supabase_url = os.environ.get("SUPABASE_URL", PADRAO_SUPABASE_URL)

    voos = buscar_voos(supabase_url, service_key)
    futuros = [v for v in voos if qualidade.prioridade(v.get("embarque")) != "passado"]

    checaveis, manuais = [], []
    for v in futuros:
        ok, problemas = qualidade.avaliar(v)
        (checaveis if ok else manuais).append((v, problemas))

    print("=" * 66)
    print("  RELATORIO DE CHECABILIDADE — %d voo(s) futuro(s)" % len(futuros))
    print("=" * 66)
    print("  Checaveis automaticamente (malha/portal) .... %d" % len(checaveis))
    print("  Precisam de atencao manual ................... %d" % len(manuais))

    por_cia = {}
    for v in futuros:
        cia = v.get("cia") or "(sem cia)"
        por_cia[cia] = por_cia.get(cia, 0) + 1
    print("\n  Por companhia:")
    for cia, qtd in sorted(por_cia.items(), key=lambda i: -i[1]):
        print("    %-10s %d" % (cia, qtd))

    if manuais:
        contagem_problema = {}
        for _, problemas in manuais:
            for p in problemas:
                if "nao impede" in p:
                    continue
                contagem_problema[p] = contagem_problema.get(p, 0) + 1
        print("\n  Motivos (voo pode ter mais de um):")
        for motivo, qtd in sorted(contagem_problema.items(), key=lambda i: -i[1]):
            print("    %-58s %d" % (motivo, qtd))

        print("\n  Lista — precisam de atencao manual:")
        for v, problemas in manuais:
            relevantes = [p for p in problemas if "nao impede" not in p]
            print("    [%s] %-8s %s %s -> %s : %s" % (
                v.get("localizador") or "?", v.get("cia") or "?",
                v.get("numero_voo") or "?", v.get("origem") or "?",
                v.get("destino") or "?", "; ".join(relevantes)))

    print("\n" + "=" * 66)


if __name__ == "__main__":
    main()
