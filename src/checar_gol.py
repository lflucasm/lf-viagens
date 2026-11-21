"""Checagem das reservas GOL no portal da companhia.

Diferente da LATAM, nao depende de PDF: localizador, origem e sobrenome ja
estao no CRM, entao a cobertura e de 100% dos localizadores GOL.

O deep link se envia sozinho - NAO clicar em nada. Basta abrir e esperar a URL
virar /minhas-viagens/detalhes-da-viagem.

POR QUE FALHA AS VEZES (medido em 29/07/2026): a API que essa pagina consome
exige score de reCAPTCHA. Navegador automatizado tira score baixo, e o score
varia por sessao - entao parte das reservas passa e parte leva
"Error recaptcha: score recaptcha is fail". Na medicao: 4 de 8 passaram.

Nao se tenta contornar o reCAPTCHA. O que passou, passou e vale; o que foi
barrado vai para a conferencia manual em src/painel.py, onde os links ja vao
preenchidos e o Chrome normal do operador abre sem problema. Nenhuma reserva
sai do monitoramento em silencio.

Uso:  .venv/bin/python src/checar_gol.py [--limite N] [--loc PNR] [--visivel]

    --loc PNR    consulta so esse(s) localizador(es), separados por virgula
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comparacao
import db
import gol
import painel
from config import config
from navegador import Navegador, NavegadorIndisponivel

ESPERA_MAXIMA = 22        # ciclos de 3s aguardando a pagina de detalhes

# Quantas recusas seguidas da companhia antes de parar a rodada. Insistir nao
# muda o resultado (a recusa e por score de reCAPTCHA, igual para todas) e
# rajada em site de companhia e o que vira bloqueio de IP - foi assim com a
# Azul. Melhor parar cedo e mandar tudo para o painel manual.
TOLERANCIA_BLOQUEIO = 3


def reservas_gol():
    """Uma entrada por localizador, com os dados que o portal exige."""
    caminho = os.path.join(config.pasta_dados, "voos_atual.csv")
    if not os.path.exists(caminho):
        print("ERRO: rode ./rodar.sh antes - falta %s" % caminho)
        sys.exit(1)

    with open(caminho, encoding="utf-8-sig") as f:
        linhas = [l for l in csv.DictReader(f)
                  if l["cia"] == "GOL" and l["prioridade"] != "passado"]

    por_localizador = {}
    for l in linhas:
        loc = l["localizador"]
        if not loc or not l["sobrenome"] or not l["origem"]:
            continue
        # o portal pede a origem do PRIMEIRO trecho da reserva
        atual = por_localizador.get(loc)
        if atual is None or l["embarque_local"] < atual["embarque_local"]:
            por_localizador[loc] = l
    return por_localizador, linhas


def main():
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}
    discreto = "--visivel" not in sys.argv

    reservas, todos_voos = reservas_gol()
    print("Voos GOL futuros no CRM ....... %d" % len(todos_voos))
    print("Localizadores consultaveis .... %d" % len(reservas))

    itens = sorted(reservas.items(), key=lambda i: i[1]["embarque_local"])
    if so_esses:
        itens = [(loc, ref) for loc, ref in itens if loc.upper() in so_esses]
        if not itens:
            print("Nenhum localizador GOL bate com %s" % ", ".join(sorted(so_esses)))
            return
    if limite is not None:      # "is not None": --limite 0 quer dizer zero
        itens = itens[:limite]
    print("Vou consultar ................. %d\n" % len(itens))

    con = db.conectar(config.caminho_banco)
    # baseline da comparacao: o que esta fonte viu da ULTIMA vez, nao o CRM
    # (ver o motivo em comparacao.comparar). Buscado uma vez so, antes de
    # qualquer registrar_observacoes desta rodada sobrescrever.
    observado_antes = db.observacoes_por_fonte(con, "portal-gol")
    ok = alertas = 0
    falhas = []          # localizadores que nao deu para conferir
    incertas = []
    barradas = []          # recusadas pela companhia (reCAPTCHA)
    seguidas = 0           # recusas consecutivas
    nao_consultadas = []   # ficaram de fora porque a rodada parou

    try:
        with Navegador(discreto=discreto, perfil_limpo=True) as nav:
            for i, (loc, ref) in enumerate(itens, 1):
                if seguidas >= TOLERANCIA_BLOQUEIO:
                    nao_consultadas.append(loc)
                    continue

                print("[%d/%d] %s  %s %s" % (i, len(itens), loc, ref["origem"],
                                             ref["sobrenome"]))
                url = gol.montar_url(loc, ref["origem"], ref["sobrenome"])
                try:
                    # o link se envia sozinho; capturamos a API que ele chama
                    # para saber o motivo quando a pagina nao abre
                    pagina = nav.abrir(url, capturar=gol.API_CONSULTA)
                    chegou = False
                    reacomodada = False
                    recusa = None
                    for _ in range(ESPERA_MAXIMA):
                        pagina.wait_for_timeout(3000)
                        if gol.URL_DETALHE in pagina.url:
                            chegou = True
                            break
                        if gol.URL_REACOMODACAO in pagina.url:
                            reacomodada = True
                            break
                        # a API ja respondeu que nao vai abrir: esperar os 66s
                        # inteiros nao muda nada
                        recusa = gol.motivo_da_falha(pagina.capturado)
                        if recusa:
                            break
                    if chegou:
                        pagina.wait_for_timeout(3000)
                    texto = pagina.inner_text("body")
                    pagina.close()
                except Exception as e:
                    print("       falhou: %s -> conferencia manual" % str(e)[:70])
                    falhas.append(loc)
                    continue

                if reacomodada:
                    # sinal explicito e definitivo - nao precisa de leitura
                    # confiavel nem do texto da pagina pra virar alerta (ver
                    # gol.URL_REACOMODACAO). Nao tentamos adivinhar qual
                    # trecho da reserva mudou - so avisamos que mudou, e quem
                    # atender confere a mao no site. Referencia o primeiro
                    # voo so porque o historico exige um voo_id.
                    voos_da_reserva = [v for v in todos_voos if v["localizador"] == loc]
                    referencia = voos_da_reserva[0] if voos_da_reserva else None
                    print("       GOL reacomodou o voo sozinha -> ALERTA")
                    if referencia:
                        db._registrar(con, referencia["id"], "alterado", "portal-gol",
                                      "alterado_pela_companhia", None,
                                      "a GOL reacomodou esta reserva automaticamente - "
                                      "verifique manualmente qual trecho mudou (%s)" % url)
                        con.commit()
                        alertas += 1
                    else:
                        falhas.append(loc)
                    seguidas = 0
                    continue

                if recusa:
                    print("       %s -> painel manual" % recusa)
                    if recusa == gol.BLOQUEIO_RECAPTCHA:
                        barradas.append(loc)
                        seguidas += 1
                        if seguidas >= TOLERANCIA_BLOQUEIO:
                            print("\n>>> %d recusas seguidas: parando a rodada da "
                                  "GOL. Insistir nao muda o resultado.\n" % seguidas)
                    else:
                        falhas.append(loc)
                    continue
                seguidas = 0

                leitura = gol.ler_pagina(texto)
                if not leitura["encontrada"]:
                    # nao afirmamos que a reserva caiu: pode ser so a pagina
                    # nao ter carregado. Vai para conferencia manual.
                    print("       nao carregou a reserva (chegou=%s) -> manual" % chegou)
                    falhas.append(loc)
                    continue

                voos_da_reserva = [v for v in todos_voos if v["localizador"] == loc]
                achados = gol.achados_de_aviso(leitura, voos_da_reserva)

                # So comparamos itinerario - e so registramos observacao - com
                # leitura confiavel. Com conexao o leitor funde trechos e
                # inventa rota: em 29/07/2026 isso gerou "rota alterada" falso
                # direto, e em 30/07/2026 gerou divergencia falsa contra a
                # malha (TSTAIX: GOL leu NAT-CWB fundido, a malha tinha NAT-GIG
                # certo) porque a observacao era gravada ANTES desta checagem.
                # Aviso explicito da pagina (cancelado etc.) continua valendo
                # mesmo sem confianca.
                if leitura.get("confiavel"):
                    achados += comparacao.comparar(leitura, voos_da_reserva, observado_antes)
                    db.registrar_observacoes(
                        con, "portal-gol",
                        comparacao.observacoes_da_leitura(leitura, voos_da_reserva))
                else:
                    print("       leitura parcial (%s) - so avisos explicitos"
                          % leitura.get("motivo"))
                    incertas.append((loc, leitura.get("motivo")))

                relevantes = [a for a in achados if a["voo_crm"]]

                if relevantes:
                    for a in relevantes:
                        print("       ALERTA [%s] %s" % (a["tipo"], a["detalhe"][:70]))
                        db._registrar(con, a["voo_crm"]["id"], "alterado",
                                      "portal-gol", a["tipo"], None, a["detalhe"])
                        alertas += 1
                    con.commit()
                else:
                    print("       OK - %s, %d trecho(s)" % (
                        leitura.get("status_pedido") or "?", len(leitura["segmentos"])))
                    ok += 1
    except NavegadorIndisponivel as e:
        print("\nERRO: %s" % e)
        sys.exit(1)
    finally:
        con.close()

    print("\n" + "=" * 62)
    print("  RESULTADO DA CHECAGEM GOL")
    print("=" * 62)
    print("  na fila ..................... %d" % len(itens))
    print("  confirmadas sem mudanca ..... %d" % ok)
    print("  com alerta .................. %d" % alertas)
    print("  leitura parcial (conexao) ... %d" % len(incertas))
    print("  barradas por reCAPTCHA ...... %d" % len(barradas))
    print("  outras falhas ............... %d" % len(falhas))
    print("  nao consultadas ............. %d" % len(nao_consultadas))
    print("=" * 62)

    # Leitura parcial tambem entra: "sem aviso explicito numa leitura que nao
    # conclui nada" nao e o mesmo que "conferido". Quem nao foi conferido com
    # seguranca vai para o painel.
    pendentes = sorted(set(barradas + nao_consultadas + falhas
                           + [l for l, _ in incertas]))
    # Rodada parcial (--limite) nao pode declarar conferido quem nem consultou.
    painel.gravar_pendencias(config.pasta_dados, "GOL", pendentes,
                             parcial=bool(limite is not None or so_esses))

    if pendentes:
        print("\n  %d reserva(s) NAO foram verificadas com seguranca e entram" % len(pendentes))
        print("  no painel manual (%s)." % ", ".join(pendentes))
        print("  No Chrome normal do operador os links funcionam:")
        print("\n      python3 src/painel.py --abrir\n")
    elif ok or alertas:
        print("\n  Carteira GOL inteira conferida automaticamente.")


if __name__ == "__main__":
    main()
