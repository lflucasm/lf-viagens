"""Checagem das reservas LATAM contra o portal da companhia.

Fluxo:
  1. le os deep links (orderId + lastname) dos PDFs da pasta da agencia
  2. abre cada um no Chrome e captura a resposta da API que a pagina consome
  3. casa com o CRM por numero do voo + data (chave unica; sobrenome e ambiguo)
  4. grava as diferencas no historico e imprime o resultado

Uso:  .venv/bin/python src/checar_latam.py [--limite N] [--loc PNR] [--invisivel]

    --loc PNR    consulta so esse(s) localizador(es), separados por virgula
"""

import csv
import os
import sys
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json

import db
import latam
import pdfs
from config import config
from navegador import Navegador, NavegadorIndisponivel

PASTA_PDFS = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/Agência de viagens /PDF RESERVAS Aéreo ")

URL_GERENCIAR = ("https://www.latamairlines.com/br/pt/minhas-viagens/"
                 "second-detail/?orderId=%s&lastname=%s")


class PastaProtegida(Exception):
    """O macOS negou a leitura da pasta de PDFs (iCloud Drive + TCC)."""


def links_do_indice(pasta_dados):
    """Deep links da LATAM lidos do indice em dados/, nao dos PDFs.

    Plano B para quando o macOS nega a pasta do iCloud. O indice e gerado por
    indexar_links.py rodado A MAO - ali o Terminal tem permissao - e fica dentro
    do projeto, onde o cron le sem restricao. Mesmo formato, mesma origem: o
    indice foi extraido desses mesmos PDFs.

    Limite honesto: PDF salvo depois do ultimo `indexar_links.py` nao esta aqui.
    Por isso a rodada avisa a idade do indice em vez de fingir cobertura total.
    """
    caminho = os.path.join(pasta_dados, "links_reservas.json")
    if not os.path.exists(caminho):
        return {}, None
    try:
        with open(caminho, encoding="utf-8") as f:
            indice = json.load(f)
    except (IOError, ValueError):
        return {}, None

    encontrados = {}
    for chave, reg in indice.items():
        url = reg.get("url") or ""
        if "latamairlines.com" not in url:
            continue
        params = dict((k.lower(), v) for k, v in pdfs.PARAMS_UTEIS.findall(url))
        pedido = (params.get("orderid") or reg.get("pedido") or "").upper()
        sobrenome = urllib.parse.unquote(params.get("lastname", "")) \
            or (reg.get("sobrenome") or "")
        if not pedido or not sobrenome:
            continue
        encontrados[pedido] = {
            "url": URL_GERENCIAR % (pedido, urllib.parse.quote(sobrenome)),
            "sobrenome": sobrenome,
            "arquivo": reg.get("arquivo") or "(indice)",
            "detalhado": True,
        }

    idade = None
    try:
        idade = (datetime.now()
                 - datetime.fromtimestamp(os.path.getmtime(caminho))).days
    except OSError:
        pass
    return encontrados, idade


def obter_links(pasta_pdfs, pasta_dados):
    """De onde vem os deep links hoje. Devolve (links, fonte, idade, aviso).

    Ordem: PDFs primeiro, porque sao a verdade mais recente. Se o macOS negar a
    pasta - o que acontece pelo cron, sem Acesso Total ao Disco - cai no indice
    em dados/, que foi extraido desses mesmos PDFs e vive dentro do projeto.

    Separado de main() para ser testavel: main() abre o Chrome, esta funcao nao
    encosta em rede nenhuma.
    """
    # os.path.isdir NAO serve de guarda: em pasta protegida por TCC ele devolve
    # True (o stat passa) e so o listdir seguinte estoura.
    if not os.path.isdir(pasta_pdfs):
        links, idade = links_do_indice(pasta_dados)
        return (links, "indice", idade,
                "Pasta de PDFs nao encontrada. Seguindo pelo indice em dados/.")
    try:
        return deep_links_latam(pasta_pdfs), "PDFs", None, None
    except PastaProtegida:
        links, idade = links_do_indice(pasta_dados)
        return (links, "indice", idade,
                "O macOS negou a leitura da pasta de PDFs no iCloud - e o que"
                " acontece pelo cron, que nao tem Acesso Total ao Disco."
                " Seguindo pelo indice em dados/links_reservas.json.")


def deep_links_latam(pasta):
    """Todos os links de gerenciamento da LATAM achados nos PDFs.

    Parte dos PDFs so traz o link do cartao de embarque
    (/cartao-de-embarque?orderId=...), que e outra pagina e nao mostra o
    itinerario. Como o que importa sao os parametros - orderId e lastName -
    montamos sempre a URL de gerenciamento a partir deles.
    """
    encontrados = {}
    try:
        arquivos = sorted(os.listdir(pasta))
    except (PermissionError, OSError):
        # A pasta fica no iCloud Drive, que o macOS protege por TCC. Rodando a
        # mao funciona (o Terminal tem permissao); pelo cron, nao - e o erro nao
        # e "pasta faltando", e "Operation not permitted". Quem chama decide o
        # que fazer: ha o indice em dados/ como plano B (ver links_do_indice).
        raise PastaProtegida(pasta)

    for nome in arquivos:
        if not nome.lower().endswith(".pdf"):
            continue
        try:
            urls = pdfs._urls(os.path.join(pasta, nome))
        except (IOError, OSError):
            continue
        for url in urls:
            if "latamairlines.com" not in url:
                continue
            params = dict((k.lower(), v) for k, v in pdfs.PARAMS_UTEIS.findall(url))
            if not params.get("orderid"):
                continue
            pedido = params["orderid"].upper()
            sobrenome = urllib.parse.unquote(params.get("lastname", ""))
            if not sobrenome:
                continue
            if pedido not in encontrados:
                encontrados[pedido] = {
                    "url": URL_GERENCIAR % (pedido, urllib.parse.quote(sobrenome)),
                    "sobrenome": sobrenome,
                    "arquivo": nome,
                    "detalhado": True,
                }
    return encontrados


CAMINHO_VINCULOS = "vinculos_latam.json"


def gravar_vinculos(novos):
    """Guarda PNR -> orderId descoberto pelo conector.

    O PDF da LATAM nao traz o PNR, so o numero de compra. Sem guardar esse
    vinculo, nenhuma outra parte do sistema consegue saber se uma reserva
    LATAM tem PDF salvo - foi o que fez 18 localizadores serem excluidos por
    engano do monitoramento em 29/07/2026.
    """
    caminho = os.path.join(config.pasta_dados, CAMINHO_VINCULOS)
    atual = {}
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                atual = json.load(f)
        except (IOError, ValueError):
            atual = {}
    atual.update(novos)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=1, sort_keys=True)
    return len(atual)


def voos_latam_do_csv():
    caminho = os.path.join(config.pasta_dados, "voos_atual.csv")
    if not os.path.exists(caminho):
        print("ERRO: rode ./rodar.sh antes - falta o %s" % caminho)
        sys.exit(1)
    with open(caminho, encoding="utf-8-sig") as f:
        return [l for l in csv.DictReader(f)
                if l["cia"] == "LATAM" and l["prioridade"] != "passado"]


def main():
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    # --loc PNR[,PNR]: consulta so esses. Mesmo uso de checar_gol.py/
    # checar_azul.py - diagnosticar ou checar sob demanda uma reserva so.
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}
    discreto = "--invisivel" in sys.argv   # janela fora da tela, nao headless

    voos = voos_latam_do_csv()
    print("Voos LATAM futuros no CRM ..... %d (%d localizadores)"
          % (len(voos), len({v["localizador"] for v in voos})))

    links, fonte, idade, aviso = obter_links(PASTA_PDFS, config.pasta_dados)
    if aviso:
        print("\n>>> %s\n" % aviso)

    if not links:
        print("ERRO: nenhum deep link disponivel.")
        print("  A pasta de PDFs esta inacessivel e o indice esta vazio ou nao existe.")
        print("  Rode a mao:  python3 src/indexar_links.py")
        sys.exit(1)

    print("Deep links LATAM (%s) ..... %d" % (fonte, len(links)))
    if idade is not None:
        print("Idade do indice ............... %d dia(s)" % idade)
        if idade > 7:
            print("   Indice velho: PDF salvo depois disso nao esta aqui.")
            print("   Rode a mao:  python3 src/indexar_links.py")

    pedidos = sorted(links.items(), key=lambda i: not i[1]["detalhado"])
    if so_esses:
        pedidos = [(loc, ref) for loc, ref in pedidos if loc.upper() in so_esses]
        if not pedidos:
            print("Nenhum localizador LATAM bate com %s" % ", ".join(sorted(so_esses)))
            sys.exit(1)
    if limite is not None:      # "is not None": --limite 0 quer dizer zero.
        pedidos = pedidos[:limite]   # com `if limite:` o 0 virava "sem limite"
                                     # e a rodada consultava os 35 pedidos.
    print("Vou consultar .................. %d\n" % len(pedidos))

    con = db.conectar(config.caminho_banco)
    # baseline da comparacao: o que esta fonte viu da ULTIMA vez, nao o CRM
    # (ver o motivo em comparacao.comparar). Buscado uma vez so, antes de
    # qualquer registrar_observacao desta rodada sobrescrever.
    observado_antes = db.observacoes_por_fonte(con, "portal-latam")
    casados, sem_casar, falhas, alertas, revisar = [], [], [], [], []
    vinculos = {}

    try:
        with Navegador(discreto=discreto, perfil_limpo=True) as nav:
            for i, (pedido, info) in enumerate(pedidos, 1):
                print("[%d/%d] %s (%s)" % (i, len(pedidos), pedido, info["arquivo"][:38]))
                dados, erro = nav.json_da_api(info["url"], latam.API_PEDIDO)

                if erro or not dados:
                    print("       falhou: %s -> conferencia manual" % (erro or "sem conteudo"))
                    falhas.append((pedido, erro))
                    continue

                leitura = latam.ler_api(dados)
                if not leitura["encontrada"]:
                    print("       reserva NAO localizada no portal")
                    falhas.append((pedido, "nao localizada"))
                    continue

                if not latam.tem_trecho_futuro(leitura):
                    print("       viagem ja realizada - fora do escopo")
                    sem_casar.append(pedido)
                    continue

                # 1o identificar a reserva; so depois comparar, e apenas contra
                # os voos DELA - comparar contra a base toda gera alarme falso
                loc, confianca = latam.identificar(leitura, voos)
                if not loc:
                    print("       sem correspondencia no CRM")
                    sem_casar.append(pedido)
                    continue
                if confianca < 4:
                    # mesmo voo e rota, data diferente: pode ser remarcacao ou
                    # pode ser outra viagem. Nao alerto sozinho - mando revisar.
                    print("       ambiguo: parece %s mas nenhuma data bate -> revisar"
                          % loc)
                    revisar.append((pedido, loc, info["arquivo"]))
                    continue

                voos_da_reserva = [v for v in voos if v["localizador"] == loc]
                por_chave = {(latam._normaliza_voo(v["numero_voo"]),
                              (v["embarque_local"] or "")[:10]): v for v in voos_da_reserva}

                # Compara ANTES de registrar: a comparacao usa a leitura
                # ANTERIOR desta fonte como baseline (observado_antes), entao
                # so pode rodar antes de este registro sobrescreve-la.
                achados = latam.comparar(leitura, voos_da_reserva, observado_antes)
                achados += latam.achados_de_status(leitura, por_chave)

                # Registra o que a LATAM mostrou, inclusive quando bate com a
                # leitura anterior - e a leitura que CONCORDA que permite depois
                # apontar outra fonte fora da linha (ver db.divergencias).
                for voo_id, partida, rota, situacao in \
                        latam.observacoes_da_leitura(leitura, voos_da_reserva):
                    db.registrar_observacao(con, voo_id, "portal-latam",
                                            partida, rota, situacao)
                con.commit()
                relevantes = [a for a in achados if a["voo_crm"]]
                print("       = %s (confianca %d, %d trecho(s) no CRM, pedido %s)"
                      % (loc, confianca, len(voos_da_reserva),
                         leitura.get("status_pedido") or "?"))

                casados.append((pedido, {loc}))
                vinculos[loc] = pedido
                problemas = [a for a in relevantes
                             if a["tipo"] not in ("verificacao_incompleta",)]
                if problemas:
                    for a in problemas:
                        loc = a["voo_crm"]["localizador"]
                        print("       ALERTA [%s] %s: %s" % (a["tipo"], loc, a["detalhe"]))
                        db._registrar(con, a["voo_crm"]["id"], "alterado", "portal-latam",
                                      a["tipo"], None, a["detalhe"])
                        alertas.append((loc, a))
                    con.commit()
                else:
                    incompletos = [a for a in relevantes
                                   if a["tipo"] == "verificacao_incompleta"]
                    print("       OK - %d trecho(s) conferido(s)%s"
                          % (len(leitura["segmentos"]),
                             ", %d nao expandido(s)" % len(incompletos) if incompletos else ""))
    except NavegadorIndisponivel as e:
        print("\nERRO: %s" % e)
        sys.exit(1)
    finally:
        con.close()

    if vinculos:
        total = gravar_vinculos(vinculos)
        print("\n>>> vinculos PNR<->orderId gravados: %d novos, %d no total"
              % (len(vinculos), total))

    locs_ok = set()
    for _, ligados in casados:
        locs_ok |= ligados
    todos = {v["localizador"] for v in voos}

    print("\n" + "=" * 62)
    print("  RESULTADO DA CHECAGEM LATAM")
    print("=" * 62)
    print("  consultas feitas ............ %d" % len(pedidos))
    print("  casaram com o CRM ........... %d" % len(casados))
    print("  sem correspondencia ......... %d" % len(sem_casar))
    print("  ambiguos (revisar) .......... %d" % len(revisar))
    print("  falharam (conferir a mao) ... %d" % len(falhas))
    print("  ALERTAS ..................... %d" % len(alertas))
    print()
    print("  localizadores LATAM cobertos  %d de %d" % (len(locs_ok), len(todos)))
    if revisar:
        print()
        print("  AMBIGUOS - conferir a mao:")
        for pedido, loc, arq in revisar:
            print("    %s  parece %s  (%s)" % (pedido, loc, arq[:40]))
    if falhas:
        print()
        print("  FALHARAM:")
        for pedido, erro in falhas:
            print("    %s  %s" % (pedido, (erro or "")[:60]))

    # Sem PDF nao ha o que checar. A lista vai para arquivo em vez do relatorio:
    # repetir 18 codigos a cada rodada vira ruido e some com o que importa.
    descobertos = sorted(todos - locs_ok)
    caminho = os.path.join(config.pasta_dados, "sem_pdf_latam.csv")
    if descobertos:
        with open(caminho, "w", encoding="utf-8-sig") as f:
            f.write("localizador\n")
            f.write("\n".join(descobertos) + "\n")
        print("  sem PDF (nao checaveis) ..... %d  -> %s"
              % (len(descobertos), os.path.basename(caminho)))
    elif os.path.exists(caminho):
        # Cobertura total: apagar em vez de deixar a lista velha no lugar. Em
        # 30/07/2026 este arquivo ficou dizendo "16 sem PDF" depois de uma
        # rodada que cobriu os 16 - quem abrisse concluiria o oposto do que
        # tinha acontecido. Arquivo desatualizado engana mais que arquivo
        # ausente.
        os.remove(caminho)
        print("  sem PDF (nao checaveis) ..... 0  (lista anterior removida)")
    print("=" * 62)


if __name__ == "__main__":
    main()
