"""Varre os PDFs das reservas e guarda todos os links de consulta encontrados.

Cada bilhete traz o link que a propria companhia gerou - com localizador,
origem e sobrenome ja embutidos. Vale mais que qualquer URL que a gente monte:
e o formato oficial, e continua valendo quando o site muda de parametro.

Este passo e 100% local: le arquivo, nao acessa site nenhum. Roda quantas
vezes quiser.

Uso:  python3 src/indexar_links.py
Saida: dados/links_reservas.csv  +  dados/links_reservas.json
"""

import csv
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pdfs
from checar_latam import PASTA_PDFS
from config import config

# host -> (companhia, para que serve)
PORTAIS = (
    ("b2c.voegol.com.br", "GOL", "reserva"),
    ("latamairlines.com", "LATAM", "reserva"),
    ("voeazul.com.br", "AZUL", "reserva"),
    ("airfrance", "AIR FRANCE", "reserva"),
    ("flytap", "TAP", "reserva"),
    ("tap.pt", "TAP", "reserva"),
    ("copaair", "COPA", "reserva"),
    ("qatarairways", "QATAR AIRWAYS", "reserva"),
    ("united.com", "UNITED", "reserva"),
    ("lufthansa", "LUFTHANSA", "reserva"),
)

# parametros que identificam a reserva, em varias grafias
CHAVES_PNR = ("pnr", "codigoreserva", "recordlocator", "bookingcode",
              "reservationcode", "localizador")
CHAVES_PEDIDO = ("orderid", "numerocompra")
CHAVES_SOBRENOME = ("lastname", "sobrenome", "surname")
CHAVES_ORIGEM = ("origem", "origin", "departure")

PNR = re.compile(r"^[A-Z0-9]{6}$")

# paginas que nao servem para conferir status
DESCARTAR = ("bagagem", "check-in", "selecionar-assentos", "cartao-de-embarque")

# O link do Smiles exige sessao logada e nao mostra status de reserva. Para GOL
# vale sempre o b2c.voegol, que abre deslogado e traz o itinerario. Quando o PDF
# so tem o do Smiles, o link e montado a partir do CRM (ver painel.py).
IGNORAR_HOSTS = ("smiles.com.br",)


def _params(url):
    partida = urllib.parse.urlparse(url)
    bruto = urllib.parse.parse_qs(partida.query)
    return {k.lower(): v[0] for k, v in bruto.items() if v}


def _companhia(url):
    for host, cia, tipo in PORTAIS:
        if host in url:
            return cia, tipo
    return None, None


def varrer(pasta):
    """Devolve lista de registros, um por link util encontrado."""
    registros = []
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith(".pdf"):
            continue
        try:
            urls = pdfs._urls(os.path.join(pasta, nome))
        except (IOError, OSError):
            continue

        for url in urls:
            if any(h in url for h in IGNORAR_HOSTS):
                continue
            cia, tipo = _companhia(url)
            if not cia:
                continue
            p = _params(url)
            if not p:
                continue

            localizador = next((p[c].upper() for c in CHAVES_PNR if p.get(c)), None)
            pedido = next((p[c].upper() for c in CHAVES_PEDIDO if p.get(c)), None)
            if not localizador and not pedido:
                continue
            if localizador and not PNR.match(localizador):
                localizador = None

            registros.append({
                "companhia": cia,
                "localizador": localizador or "",
                "pedido": pedido or "",
                "sobrenome": next((urllib.parse.unquote(p[c])
                                   for c in CHAVES_SOBRENOME if p.get(c)), ""),
                "origem": next((p[c].upper() for c in CHAVES_ORIGEM if p.get(c)), ""),
                "util": "nao" if any(d in url for d in DESCARTAR) else "sim",
                "arquivo": nome,
                "url": url,
            })
    return registros


def melhores(registros):
    """Um link por reserva: o de consulta de status vence o de bagagem."""
    escolhidos = {}
    for r in registros:
        chave = r["localizador"] or r["pedido"]
        atual = escolhidos.get(chave)
        if atual is None or (atual["util"] == "nao" and r["util"] == "sim"):
            escolhidos[chave] = r
    return escolhidos


def main():
    if not os.path.isdir(PASTA_PDFS):
        print("ERRO: pasta de PDFs nao encontrada:\n  %s" % PASTA_PDFS)
        sys.exit(1)

    registros = varrer(PASTA_PDFS)
    escolhidos = melhores(registros)

    if not os.path.isdir(config.pasta_dados):
        os.makedirs(config.pasta_dados)
    csv_saida = os.path.join(config.pasta_dados, "links_reservas.csv")
    json_saida = os.path.join(config.pasta_dados, "links_reservas.json")

    colunas = ["companhia", "localizador", "pedido", "sobrenome", "origem",
               "util", "arquivo", "url"]
    linhas = sorted(escolhidos.values(),
                    key=lambda r: (r["companhia"], r["localizador"] or r["pedido"]))
    with open(csv_saida, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas)
    with open(json_saida, "w", encoding="utf-8") as f:
        json.dump(escolhidos, f, ensure_ascii=False, indent=1)

    # cruzamento com o que esta ativo no CRM
    ativos = {}
    caminho_voos = os.path.join(config.pasta_dados, "voos_atual.csv")
    if os.path.exists(caminho_voos):
        with open(caminho_voos, encoding="utf-8-sig") as f:
            for l in csv.DictReader(f):
                if l["prioridade"] != "passado" and l["localizador"]:
                    ativos[l["localizador"].upper()] = l["cia"]

    por_cia = {}
    for r in linhas:
        por_cia[r["companhia"]] = por_cia.get(r["companhia"], 0) + 1

    print("PDFs varridos ............ %d" % len(os.listdir(PASTA_PDFS)))
    print("links de consulta ........ %d" % len(registros))
    print("reservas distintas ....... %d" % len(escolhidos))
    print()
    print("--- por companhia ---")
    for cia, n in sorted(por_cia.items(), key=lambda i: -i[1]):
        print("  %-16s %d" % (cia, n))

    if ativos:
        com_link = [p for p in ativos if p in escolhidos]
        print()
        print("--- cruzamento com o CRM ---")
        print("  localizadores ativos ..... %d" % len(ativos))
        print("  com link no PDF .......... %d" % len(com_link))
        faltando = sorted(set(ativos) - set(escolhidos))
        if faltando:
            print("  sem PDF salvo ............ %d" % len(faltando))

    print()
    print("  %s" % csv_saida)


if __name__ == "__main__":
    main()
