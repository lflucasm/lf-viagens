"""Fase 1: le os voos do MilhasFlow, guarda no banco e gera o CSV do dia.

Uso:  python3 src/sync.py
"""

import csv
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import fusos
import qualidade
from config import config
from milhasflow import ErroMilhasFlow, MilhasFlow

COLUNAS_CSV = [
    "localizador", "passageiros", "sobrenome", "cliente", "cia", "numero_voo",
    "origem", "destino", "embarque_local", "chegada_local", "classe", "sentido",
    "status", "dias_para_voo", "prioridade", "checavel", "problemas",
    "balcao", "tags", "valor_venda", "embarque_utc", "emissao_id", "id",
]


CHAVES_NOME = ("name", "nome", "full_name", "nome_completo", "passenger_name")

# O MilhasFlow grava passengers_data em dois formatos:
#   A) [{"name": "..."}]
#   B) {"flightGroups": [[{"name","cpf","birthDate"}]], "hotels": [...], ...}
# Em B os passageiros ficam so dentro de flightGroups - as outras chaves
# guardam hotel, seguro e locacao, e o "name" delas nao e de gente.
CHAVES_GRUPO = ("passengers", "passageiros", "flightGroups")


def _coletar_nomes(no, encontrados):
    if isinstance(no, str):
        if no.strip():
            encontrados.append(no.strip())
    elif isinstance(no, list):
        for item in no:
            _coletar_nomes(item, encontrados)
    elif isinstance(no, dict):
        for chave in CHAVES_NOME:
            valor = no.get(chave)
            if isinstance(valor, str) and valor.strip():
                encontrados.append(valor.strip())
                return
        grupos = [no[c] for c in CHAVES_GRUPO if no.get(c)]
        for grupo in (grupos or [v for v in no.values() if isinstance(v, (list, dict))]):
            _coletar_nomes(grupo, encontrados)


def _nomes_passageiros(dados):
    """Extrai os nomes dos passageiros, seja qual for o formato gravado."""
    if not dados:
        return ""
    if isinstance(dados, str):
        try:
            dados = json.loads(dados)
        except ValueError:
            return dados.strip()

    encontrados = []
    _coletar_nomes(dados, encontrados)

    unicos = []
    for nome in encontrados:
        if nome not in unicos:  # o mesmo passageiro repete a cada trecho
            unicos.append(nome)
    return " / ".join(unicos)


def montar_voos(voos_api, emissoes_api, tags_por_emissao=None, ignorados=None,
                nomes_voucher=None):
    """Junta reminders + emissions no formato do banco.

    `ignorados`: localizadores fora do monitoramento (padrao: ignorados.txt).
    `nomes_voucher`: {emission_id ou localizador: nomes} lidos do PDF anexado
    na venda (vouchers.nomes_por_reserva) - so a ingestao da nuvem passa.
    """
    tags_por_emissao = tags_por_emissao or {}
    nomes_voucher = nomes_voucher or {}
    fora_do_monitoramento = config.ignorados if ignorados is None else ignorados
    emissoes = {}
    for e in emissoes_api:
        cliente = e.get("client") or {}
        if isinstance(cliente, list):
            cliente = cliente[0] if cliente else {}
        emissoes[e["id"]] = {
            "cliente": (cliente or {}).get("name") or "",
            "passageiros": _nomes_passageiros(e.get("passengers_data")),
            "localizador_emissao": e.get("localizador") or "",
            "valor_venda": e.get("sale_value"),
            "tags": tags_por_emissao.get(e["id"], []),
        }

    resultado = []
    descartados = ignorados = 0
    for v in voos_api:
        # a tabela mistura trecho aereo com terrestre (rodoviaria, trem);
        # so aeroporto tem o que checar em site de companhia
        if not (fusos.e_aeroporto(v.get("departure_airport"))
                and fusos.e_aeroporto(v.get("arrival_airport"))):
            descartados += 1
            continue

        emissao = emissoes.get(v.get("emission_id"), {})
        etiquetas = emissao.get("tags") or []
        codigo = (v.get("locator") or emissao.get("localizador_emissao") or "").strip().upper()
        if codigo and codigo in fora_do_monitoramento:
            ignorados += 1
            continue
        # o localizador do trecho manda; o da emissao e a rede de seguranca
        localizador = (v.get("locator") or emissao.get("localizador_emissao") or "").strip().upper()

        resultado.append({
            "id": v["id"],
            "emissao_id": v.get("emission_id"),
            "localizador": localizador,
            "cia": qualidade.normalizar_cia(v.get("airline")) or "",
            "numero_voo": (v.get("flight_number") or "").strip(),
            "origem": v.get("departure_airport") or "",
            "destino": v.get("arrival_airport") or "",
            "embarque": v.get("departure_datetime") or "",
            "chegada": v.get("arrival_datetime") or "",
            "classe": v.get("cabin_class") or "",
            "sentido": v.get("flight_direction") or "",
            "status": v.get("status") or "",
            "cliente": emissao.get("cliente", ""),
            # emissao com passengers_data sem nome (37 de 180 trechos futuros
            # em 07/10/2026, ex. TSTAGX) some da busca por passageiro do
            # painel. Ordem: venda > voucher anexado (nome completo de todos)
            # > passenger_name do trecho (as vezes so sobrenome: "De Miranda")
            "passageiros": (emissao.get("passageiros")
                            or nomes_voucher.get(v.get("emission_id"))
                            or nomes_voucher.get(localizador)
                            or (v.get("passenger_name") or "").strip()),
            "valor_venda": emissao.get("valor_venda"),
            "tags": " | ".join(etiquetas),
            # venda para outra agencia: checa igual, mas quem avisa o
            # passageiro e a agencia parceira
            "balcao": 1 if any("BALC" in t.upper() for t in etiquetas) else 0,
        })

    if descartados:
        print("  %d trechos terrestres ignorados (rodoviaria/trem)." % descartados)
    if ignorados:
        print("  %d trechos de localizadores em ignorados.txt (fora do monitoramento)."
              % ignorados)
    return resultado


def gravar_csv(voos, pasta):
    if not os.path.isdir(pasta):
        os.makedirs(pasta)

    linhas = []
    for v in voos:
        checavel, problemas = qualidade.avaliar(v)
        dias = qualidade.dias_para_voo(v.get("embarque"))
        linha = dict(v)
        linha["sobrenome"] = qualidade.sobrenome(v.get("passageiros"))
        # o banco guarda UTC; quem le a planilha quer a hora do aeroporto
        linha["embarque_local"] = fusos.texto_local(v.get("embarque"), v.get("origem"))
        linha["chegada_local"] = fusos.texto_local(v.get("chegada"), v.get("destino"))
        linha["embarque_utc"] = v.get("embarque") or ""
        linha["dias_para_voo"] = "" if dias is None else dias
        linha["prioridade"] = qualidade.prioridade(v.get("embarque"))
        linha["checavel"] = "sim" if checavel else "NAO"
        linha["problemas"] = "; ".join(problemas)
        linhas.append(linha)

    linhas.sort(key=lambda l: (l.get("embarque") or "9999"))

    hoje = datetime.now().strftime("%Y-%m-%d")
    caminhos = [
        os.path.join(pasta, "voos_%s.csv" % hoje),
        os.path.join(pasta, "voos_atual.csv"),
    ]
    for caminho in caminhos:
        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS_CSV, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(linhas)

    pendencias = [l for l in linhas if l["checavel"] == "NAO" and l["prioridade"] != "passado"]
    caminho_pend = os.path.join(pasta, "pendencias_%s.csv" % hoje)
    if pendencias:
        with open(caminho_pend, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS_CSV, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(pendencias)

    return caminhos[0], (caminho_pend if pendencias else None), linhas


def relatorio(linhas, novos, alterados, sumiram):
    futuros = [l for l in linhas if l["prioridade"] != "passado"]
    checaveis = [l for l in futuros if l["checavel"] == "sim"]
    com_numero = [l for l in futuros if l.get("numero_voo")]

    print("\n" + "=" * 62)
    print("  RESUMO DA SINCRONIZACAO")
    print("=" * 62)
    print("  Trechos lidos no MilhasFlow ....... %d" % len(linhas))
    print("  Voos futuros ...................... %d" % len(futuros))
    print("  Checaveis automaticamente ......... %d" % len(checaveis))
    print("  Com numero do voo preenchido ...... %d de %d" % (len(com_numero), len(futuros)))

    print("\n  Por prioridade (proximidade do embarque):")
    for nivel in ("critica", "alta", "media", "baixa", "indefinida"):
        qtd = len([l for l in futuros if l["prioridade"] == nivel])
        if qtd:
            print("    %-12s %d" % (nivel, qtd))

    problemas = {}
    for l in futuros:
        if l["checavel"] == "NAO":
            for p in l["problemas"].split("; "):
                if p and "nao impede" not in p:
                    problemas[p] = problemas.get(p, 0) + 1
    if problemas:
        print("\n  Impedem a checagem automatica:")
        for p, qtd in sorted(problemas.items(), key=lambda x: -x[1]):
            print("    %-46s %d" % (p, qtd))

    if novos or alterados or sumiram:
        print("\n  Mudancas desde a ultima execucao:")
        print("    novos ....... %d" % len(novos))
        print("    alterados ... %d" % len(alterados))
        print("    sumiram ..... %d" % len(sumiram))
        for v in alterados[:10]:
            for campo, de, para in v["mudancas"]:
                print("      [%s] %s: %s -> %s" % (v.get("localizador") or "?", campo, de, para))
        for v in sumiram[:10]:
            print("      [%s] sumiu do CRM (%s %s)" % (
                v.get("localizador") or "?", v.get("origem"), v.get("destino")))
    else:
        print("\n  Nenhuma mudanca desde a ultima execucao.")
    print("=" * 62 + "\n")


def main():
    config.validar()
    cliente = MilhasFlow(config)

    print("Conectando ao MilhasFlow...")
    try:
        voos_api = cliente.buscar_voos()
        emissoes_api = cliente.buscar_emissoes()
        tags_api = cliente.buscar_tags()
    except ErroMilhasFlow as e:
        print("\nERRO ao consultar o MilhasFlow:\n  %s\n" % e)
        sys.exit(1)

    print("  %d trechos e %d emissoes recebidos." % (len(voos_api), len(emissoes_api)))

    voos = montar_voos(voos_api, emissoes_api, tags_api)

    con = db.conectar(config.caminho_banco)
    novos, alterados, sumiram = db.sincronizar(con, voos, ignorados=config.ignorados)
    db.registrar_execucao(con, len(voos), len(novos), len(alterados), len(sumiram))

    caminho_csv, caminho_pend, linhas = gravar_csv(voos, config.pasta_dados)
    con.close()

    relatorio(linhas, novos, alterados, sumiram)
    print("  CSV ......... %s" % caminho_csv)
    print("  (copia fixa)  %s" % os.path.join(config.pasta_dados, "voos_atual.csv"))
    if caminho_pend:
        print("  Pendencias .. %s" % caminho_pend)
    print("  Banco ....... %s\n" % config.caminho_banco)


if __name__ == "__main__":
    main()
