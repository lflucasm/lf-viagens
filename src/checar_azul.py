"""Checagem das reservas Azul no portal da companhia.

Como a GOL e ao contrario da LATAM, nao depende de PDF: localizador e origem
ja estao no CRM. E a Azul nem sobrenome pede, entao a cobertura e de 100% dos
localizadores Azul.

Le a API canonica que a pagina consome, nao a tela:

    b2c-api.voeazul.com.br/canonical/api/booking/v5/bookings/<PNR>

Validado contra resposta real em 30/07/2026. O texto da pagina e quase todo
oferta de hotel e cupom - a API traz o itinerario inteiro estruturado.

POR QUE ESTE CONECTOR E O MAIS CAUTELOSO DOS TRES

Foi a Azul que limitou o IP da agencia em 29/07/2026, depois de uma rajada de
acessos automatizados. Dai:

  - a quarentena e conferida ANTES de abrir o Chrome
  - duas recusas seguidas param a rodada (a GOL tolera tres)
  - HTTP 403/429 ou aviso de bloqueio na pagina poe o dominio de quarentena e
    interrompe tudo na hora
  - teto de 20 reservas por rodada, folga sobre o limite de 40/h do limitador

Uso:
    .venv/bin/python src/checar_azul.py [--limite N] [--loc PNR] [--visivel]
                                       [--capturar]

    --loc PNR    consulta so esse(s) localizador(es), separados por virgula
    --capturar   grava a pagina e as respostas de API em dados/, para
                 diagnostico. Nao interpreta nada e nao gera alerta.
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import azul
import comparacao
import db
import limitador
import painel
from config import config
from navegador import Navegador, NavegadorIndisponivel

# Ciclos de 3s aguardando a resposta da reserva. 30s nao bastavam: em
# 30/07/2026 as reservas de 4 trechos (que disparam 6 chamadas de API) nao
# chegavam a tempo e apareciam como "nao trouxe a reserva" - falso negativo que
# mandava reserva intacta para o painel. O goto do navegador ja tem teto de 45s.
ESPERA_MAXIMA = 20

# Quantas recusas seguidas antes de parar. Mais rigido que a GOL de proposito:
# insistir com a Azul foi o que custou o IP da agencia.
TOLERANCIA_BLOQUEIO = 2

# Teto de reservas por rodada. O limitador ja impoe 40 consultas/hora ao
# dominio da Azul; este teto e a folga para nunca chegar perto dele.
TETO_POR_RODADA = 20


def reservas_azul():
    """Uma entrada por localizador, com os dados que o portal exige.

    A Azul pede so PNR + aeroporto de origem - sobrenome nao entra
    (ver qualidade.REQUISITOS).
    """
    caminho = os.path.join(config.pasta_dados, "voos_atual.csv")
    if not os.path.exists(caminho):
        print("ERRO: rode ./rodar.sh antes - falta %s" % caminho)
        sys.exit(1)

    with open(caminho, encoding="utf-8-sig") as f:
        linhas = [l for l in csv.DictReader(f)
                  if l["cia"] == "AZUL" and l["prioridade"] != "passado"]

    por_localizador = {}
    for l in linhas:
        loc = l["localizador"]
        if not loc or not l["origem"]:
            continue
        # o portal pede a origem do PRIMEIRO trecho ainda nao voado; como o CSV
        # ja exclui o passado, o menor embarque e esse trecho
        atual = por_localizador.get(loc)
        if atual is None or l["embarque_local"] < atual["embarque_local"]:
            por_localizador[loc] = l
    return por_localizador, linhas


def gravar_amostra(loc, texto, capturado):
    """Guarda a leitura crua para calibrar o parser depois.

    Vai para dados/ (ignorado pelo git) e nao para testes/paginas/: a pagina
    traz nome de passageiro e o operador decide conscientemente o que vira
    caso de teste versionado.
    """
    base = os.path.join(config.pasta_dados, "azul_%s" % loc.lower())
    escritos = []
    if texto:
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(texto)
        escritos.append(base + ".txt")
    if capturado:
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(capturado, f, ensure_ascii=False, indent=1, default=str)
        escritos.append(base + ".json")
    return escritos


def main():
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    # --loc PNR[,PNR]: consulta so esses. Serve para diagnosticar uma reserva
    # sem gastar consulta com as outras - com a Azul, consulta e recurso caro.
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}
    discreto = "--visivel" not in sys.argv
    capturar = "--capturar" in sys.argv

    # Conferir a quarentena antes de abrir o Chrome: se a Azul esta barrada,
    # abrir navegador so para descobrir isso e gasto - e a tentacao de "so uma
    # consulta para testar" e exatamente o que gerou o bloqueio.
    url_teste = azul.montar_url("XXXXXX", "XXX")
    bloqueado, faltam = limitador.esta_bloqueado(url_teste)
    if bloqueado:
        print("A Azul esta em quarentena por mais %d min (%.1f h)." % (faltam, faltam / 60.0))
        print("Bloqueio registrado por rodada anterior - nao se insiste com a Azul.")
        print("\nEnquanto isso, a conferencia e manual:")
        print("\n    python3 src/painel.py --abrir\n")
        sys.exit(2)

    reservas, todos_voos = reservas_azul()
    print("Voos AZUL futuros no CRM ...... %d" % len(todos_voos))
    print("Localizadores consultaveis .... %d" % len(reservas))

    itens = sorted(reservas.items(), key=lambda i: i[1]["embarque_local"])
    if so_esses:
        itens = [(loc, ref) for loc, ref in itens if loc.upper() in so_esses]
        if not itens:
            print("Nenhum localizador Azul bate com %s" % ", ".join(sorted(so_esses)))
            sys.exit(1)
    if limite:
        itens = itens[:limite]
    if len(itens) > TETO_POR_RODADA:
        print("  (teto de %d por rodada; %d ficam para a proxima)"
              % (TETO_POR_RODADA, len(itens) - TETO_POR_RODADA))
        itens = itens[:TETO_POR_RODADA]
    print("Vou consultar ................. %d\n" % len(itens))

    con = db.conectar(config.caminho_banco)
    # baseline da comparacao: o que esta fonte viu da ULTIMA vez, nao o CRM
    # (ver o motivo em comparacao.comparar). Buscado uma vez so, antes de
    # qualquer registrar_observacoes desta rodada sobrescrever.
    observado_antes = db.observacoes_por_fonte(con, "portal-azul")
    ok = alertas = capturadas = 0
    falhas = []          # localizadores que nao deu para conferir
    incertas = []
    barradas = []
    amostras = []
    seguidas = 0
    nao_consultadas = []
    interrompido = None

    try:
        with Navegador(discreto=discreto, perfil_limpo=True) as nav:
            for i, (loc, ref) in enumerate(itens, 1):
                if interrompido or seguidas >= TOLERANCIA_BLOQUEIO:
                    nao_consultadas.append(loc)
                    continue

                print("[%d/%d] %s  %s" % (i, len(itens), loc, ref["origem"]))
                url = azul.montar_url(loc, ref["origem"])
                try:
                    pagina = nav.abrir(url, capturar=azul.API_CAPTURA)
                    recusa = e_bloqueio = None
                    esperou = 0
                    for _ in range(ESPERA_MAXIMA):
                        pagina.wait_for_timeout(3000)
                        esperou += 3
                        recusa, e_bloqueio = azul.motivo_da_falha(pagina.capturado)
                        # a reserva ja chegou: nao ha o que esperar
                        if recusa or azul.resposta_do_booking(pagina.capturado):
                            break
                    texto = pagina.inner_text("body")
                    capturado = dict(pagina.capturado)
                    pagina.close()
                except limitador.LimiteExcedido as e:
                    print("       %s" % e)
                    interrompido = str(e)
                    continue
                except Exception as e:
                    print("       falhou: %s -> conferencia manual" % str(e)[:70])
                    falhas.append(loc)
                    continue

                if capturar:
                    escritos = gravar_amostra(loc, texto, capturado)
                    amostras += escritos
                    print("       amostra gravada: %s"
                          % ", ".join(os.path.basename(e) for e in escritos))

                # Bloqueio na propria pagina: poe o dominio de quarentena e para
                # a rodada inteira. Com a Azul nao se testa "so mais uma".
                sinal = azul.sinal_de_bloqueio(texto)
                if sinal or e_bloqueio:
                    limitador.registrar_bloqueio(url)
                    interrompido = ("a Azul bloqueou o acesso (%s). Dominio em "
                                    "quarentena, rodada interrompida."
                                    % (sinal or recusa))
                    print("       %s" % interrompido)
                    barradas.append(loc)
                    continue

                if recusa:
                    print("       %s -> painel manual" % recusa)
                    barradas.append(loc)
                    seguidas += 1
                    if seguidas >= TOLERANCIA_BLOQUEIO:
                        print("\n>>> %d recusas seguidas: parando a rodada da Azul.\n"
                              % seguidas)
                    continue
                seguidas = 0

                if capturar:
                    # captura nao confere nada: so guarda o material bruto.
                    capturadas += 1
                    continue

                # "nao respondeu a tempo" e "respondeu sem reserva" sao coisas
                # diferentes, e chamar as duas de a mesma coisa esconde qual
                # esta acontecendo. Nenhuma das duas vira "cancelado".
                booking = azul.resposta_do_booking(capturado)
                if booking is None:
                    print("       a API nao respondeu em %ds (%d chamada[s] vista[s])"
                          " -> conferencia manual" % (esperou, len(capturado)))
                    falhas.append(loc)
                    continue

                leitura = azul.ler_api(booking.get("json"))
                if not leitura["encontrada"]:
                    print("       a API respondeu mas sem itinerario -> manual")
                    falhas.append(loc)
                    continue

                # O PNR volta na resposta: se vier outro, paramos. Comparar a
                # reserva errada com o CRM e como alertar contra a base inteira.
                devolvido = (leitura.get("localizador") or "").upper()
                if devolvido and devolvido != loc.upper():
                    print("       a API devolveu %s, esperado %s -> manual"
                          % (devolvido, loc))
                    falhas.append(loc)
                    continue

                voos_da_reserva = [v for v in todos_voos if v["localizador"] == loc]
                achados = azul.achados_de_aviso(leitura, voos_da_reserva)

                # Comparacao de itinerario - e registro de observacao - so com
                # leitura confiavel, pelo mesmo motivo detalhado em
                # checar_gol.py: leitura duvidosa que vira "fonte" para efeito
                # de cruzamento gera divergencia falsa. Vale aqui mesmo que a
                # Azul nao funda trechos hoje. Aviso explicito continua passando.
                if leitura.get("confiavel"):
                    achados += comparacao.comparar(leitura, voos_da_reserva, observado_antes)
                    db.registrar_observacoes(
                        con, "portal-azul",
                        comparacao.observacoes_da_leitura(leitura, voos_da_reserva))
                else:
                    print("       leitura parcial (%s) - so avisos explicitos"
                          % leitura.get("motivo"))
                    incertas.append((loc, leitura.get("motivo")))
                    if not amostras:
                        amostras += gravar_amostra(loc, texto, capturado)

                relevantes = [a for a in achados if a["voo_crm"]]
                if relevantes:
                    for a in relevantes:
                        print("       ALERTA [%s] %s" % (a["tipo"], a["detalhe"][:70]))
                        db._registrar(con, a["voo_crm"]["id"], "alterado",
                                      "portal-azul", a["tipo"], None, a["detalhe"])
                        alertas += 1
                    con.commit()
                elif leitura.get("confiavel"):
                    print("       OK - %s, %d trecho(s)" % (
                        leitura.get("status_pedido") or "?", len(leitura["segmentos"])))
                    ok += 1
                else:
                    # Sem aviso na tela E sem leitura confiavel nao e "esta tudo
                    # bem": e "nao consegui olhar direito". Confundir os dois e o
                    # pior resultado possivel, entao esta reserva NAO entra na
                    # conta de conferidas - ela vai para o painel manual.
                    print("       sem aviso na pagina, mas a leitura nao conclui nada")
    except NavegadorIndisponivel as e:
        print("\nERRO: %s" % e)
        sys.exit(1)
    except limitador.LimiteExcedido as e:
        print("\nPARADO: %s" % e)
        interrompido = str(e)
    finally:
        con.close()

    print("\n" + "=" * 62)
    print("  RESULTADO DA CHECAGEM AZUL")
    print("=" * 62)
    print("  na fila ..................... %d" % len(itens))
    if capturar:
        print("  amostras capturadas ......... %d" % capturadas)
    print("  conferidas sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d" % alertas)
    print("  lidas sem conclusao ......... %d" % len(incertas))
    print("  recusadas/bloqueadas ........ %d" % len(barradas))
    print("  outras falhas ............... %d" % len(falhas))
    print("  nao consultadas ............. %d" % len(nao_consultadas))
    print("=" * 62)

    if interrompido:
        print("\n  RODADA INTERROMPIDA: %s" % interrompido)

    if amostras:
        print("\n  Amostras gravadas para diagnostico:")
        for caminho in sorted(set(amostras)):
            print("    %s" % caminho)

    pendentes = sorted(set(barradas + nao_consultadas + falhas
                           + [l for l, _ in incertas]))
    # So faz sentido declarar "o resto esta coberto" quando a rodada olhou a
    # carteira inteira. Com --loc ou --limite, quem ficou de fora nao foi
    # conferido nem falhou - nao da para dizer nada sobre ele.
    parcial = bool(so_esses or limite or capturar)
    painel.gravar_pendencias(config.pasta_dados, "AZUL", pendentes, parcial)

    if pendentes:
        print("\n  %d reserva(s) NAO foram verificadas e entram no painel" % len(pendentes))
        print("  manual (%s):" % ", ".join(pendentes))
        print("\n      python3 src/painel.py --abrir\n")


if __name__ == "__main__":
    main()
