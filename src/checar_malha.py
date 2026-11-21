"""Checagem pela malha publicada: numero do voo + data, sem localizador.

Cobre 100% dos voos futuros do CRM, de qualquer companhia - inclusive as que
nao tem conector (TAP, Copa, AF, Qatar) e as reservas GOL que o reCAPTCHA
barra. Ver malha.py para o que esta fonte ve e o que ela nao ve.

Uma chamada por numero de voo + data, nao por reserva: duas reservas no mesmo
voo custam uma consulta so.

A COTA E O QUE MANDA NA CADENCIA. O endpoint de voo e TIER 2: custa 2 unidades
por consulta, e o plano BASIC do RapidAPI da 600 unidades/mes - 300 consultas,
ou ~10 por dia. Conferir os 47 voos futuros todo dia pediria 2.820 unidades/mes.

Entao a rodada NAO varre a lista: ela gasta o orcamento do dia nos voos mais
atrasados, por rotacao (ver malha.priorizar e db.malha_checagens). Uma chamada
por dia basta - a propria rodada escolhe o que conferir.

A prioridade vem da operacao da agencia. A PROPORCAO e fixa; a escala nao:

    voo com < 8 dias    nao confere - a equipe ja acompanha pelo CRM, que abre
                        o voo para check-in e manipulacao
    voo em 8-30 dias    a cada 3 dias   \
    voo em 31-90 dias   a cada 7 dias    > proporcao 3:7:14, escalada para
    voo com 90+ dias    a cada 14 dias  /  caber no credito (malha.ajustar_faixas)

Carteira pequena aproxima as conferencias, carteira grande as espaca - sempre
mantendo a relacao entre as faixas. Sem isso, intervalo fixo ou deixaria credito
parado ou estouraria a cota no dia 20, e a carteira muda toda semana.

O orcamento do dia sai do SALDO REAL que a API informa, dividido pelos dias que
faltam para renovar - entao teste manual e rodada de outra maquina ja entram na
conta sozinhos.

Alteracao e cancelamento chegam quase sempre em voo distante - e voo distante
que muda tambem da tempo de reagir, por isso o intervalo maior nao custa nada:
a comparacao e sempre contra o CRM, nunca contra a checagem anterior, entao
intervalo maior atrasa a noticia, nao a perde.

Uso:
    .venv/bin/python src/checar_malha.py                # a rodada do dia
    .venv/bin/python src/checar_malha.py --plano        # mostra o que faria
    .venv/bin/python src/checar_malha.py --orcamento 40 # gastar mais hoje
    .venv/bin/python src/checar_malha.py --tudo         # ignora a rotacao
    .venv/bin/python src/checar_malha.py --cia GOL      # so uma companhia
    .venv/bin/python src/checar_malha.py --limite 5     # experimentar barato
    .venv/bin/python src/checar_malha.py --seco         # nao grava alerta
"""

import csv
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agenda
import comparacao
import db
import malha
from config import config
from provedor_malha import MalhaIndisponivel, ProvedorMalha

# Orcamento de partida, usado so na primeira rodada - dali em diante o numero
# vem do SALDO REAL que a API informa, dividido pelos dias que faltam para a
# cota renovar. Assim o gasto manual, o teste e a rodada de outra maquina ja
# entram na conta sem ninguem precisar ajustar constante nenhuma.
ORCAMENTO_DIARIO = 20

# Piso de cota: abaixo disso a rodada para, para o mes nao acabar no dia 10.
RESERVA_UNIDADES = 40


def orcamento_do_dia(con, provedor, pedido=None):
    """Quanto gastar hoje. Devolve (unidades, explicacao).

    Preferencia pelo saldo real do fornecedor: ele ja desconta tudo que foi
    gasto, por qualquer caminho. Sem saldo conhecido (primeira rodada), cai no
    ORCAMENTO_DIARIO.
    """
    if pedido is not None:
        return pedido, "pedido na linha de comando"

    cota = db.cota_malha(con)
    if not cota or cota.get("restantes") is None:
        return ORCAMENTO_DIARIO, "padrao (a API ainda nao informou saldo)"

    restantes = cota["restantes"]
    dias = malha.DIAS_DO_CICLO
    if cota.get("reset_em"):
        try:
            alvo = datetime.fromisoformat(cota["reset_em"])
            dias = max(1, (alvo - datetime.now()).days + 1)
        except (ValueError, TypeError):
            pass

    disponivel = max(0, restantes - RESERVA_UNIDADES)
    return (int(disponivel / dias),
            "saldo real %d - reserva %d, em %d dia(s) ate renovar"
            % (restantes, RESERVA_UNIDADES, dias))


def voos_para_checar(cia=None, dias=None):
    """Um item por (numero de voo, data). Cada item leva os voos do CRM que
    caem nele - normalmente um, mas duas reservas podem usar o mesmo voo.

    Devolve (grupos, fora_do_horizonte, dias_por_chave).
    """
    caminho = os.path.join(config.pasta_dados, "voos_atual.csv")
    if not os.path.exists(caminho):
        print("ERRO: rode ./rodar.sh antes - falta %s" % caminho)
        sys.exit(1)

    with open(caminho, encoding="utf-8-sig") as f:
        linhas = [l for l in csv.DictReader(f) if l["prioridade"] != "passado"]

    limite_dias = dias if dias is not None else config.malha_dias
    grupos = {}
    dias_por_chave = {}
    fora_do_horizonte = 0
    for l in linhas:
        if cia and l["cia"].upper() != cia.upper():
            continue
        if not l["numero_voo"] or not l["embarque_local"]:
            continue
        try:
            antecedencia = int(l["dias_para_voo"])
        except (ValueError, TypeError):
            antecedencia = None
        if antecedencia is not None and antecedencia > limite_dias:
            fora_do_horizonte += 1
            continue
        chave = (l["numero_voo"].strip(), l["embarque_local"][:10])
        grupos.setdefault(chave, []).append(l)
        # o menor: numa reserva com varios trechos, manda o que embarca antes
        if antecedencia is not None:
            atual = dias_por_chave.get(chave)
            if atual is None or antecedencia < atual:
                dias_por_chave[chave] = antecedencia

    ordenado = sorted(grupos.items(), key=lambda i: i[0][1])
    return ordenado, fora_do_horizonte, dias_por_chave


def main():
    cia = None
    if "--cia" in sys.argv:
        cia = sys.argv[sys.argv.index("--cia") + 1]
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    dias = None
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])
    orcamento_pedido = None
    if "--orcamento" in sys.argv:
        orcamento_pedido = int(sys.argv[sys.argv.index("--orcamento") + 1])
    tudo = "--tudo" in sys.argv
    plano = "--plano" in sys.argv
    seco = "--seco" in sys.argv or plano

    # Uma malha de cada vez: o vigia acorda a cada 30 min e so ve a agenda
    # marcada quando esta aqui termina, entao sem trava ele dispara uma segunda
    # por cima da que o launchd comecou as 8h - duas gastando a mesma cota. Uma
    # consulta de plano (--plano/--seco) nao gasta nada e nao precisa esperar.
    if not seco and not agenda.travar("malha"):
        print("Ja tem uma checagem de malha em andamento. Saindo.")
        return

    provedor = ProvedorMalha(config.malha_url, config.malha_header, config.malha_key)
    if not provedor.configurado():
        print("ERRO: a consulta de malha nao esta configurada.\n")
        print("  Abra o .env e preencha MALHA_API_KEY.")
        print("  MALHA_API_URL e MALHA_API_HEADER ja vem com o padrao do")
        print("  canal API.market; troque se voce assinou por outro canal.\n")
        sys.exit(1)

    grupos, fora, dias_por_chave = voos_para_checar(cia, dias)
    horizonte = dias if dias is not None else config.malha_dias
    print("Voos futuros no horizonte ..... %d" % len(grupos))
    if fora:
        print("Fora do horizonte (%d dias) ... %d" % (horizonte, fora))

    con = db.conectar(config.caminho_banco)
    # baseline da comparacao: o que esta fonte viu da ULTIMA vez, nao o CRM
    # (ver o motivo em comparacao.comparar). Buscado uma vez so, antes de
    # qualquer registrar_observacao desta rodada sobrescrever.
    observado_antes = db.observacoes_por_fonte(con, "malha")

    orcamento, porque = orcamento_do_dia(con, provedor, orcamento_pedido)
    print("Orcamento de hoje ............. %d unidades (%s)" % (orcamento, porque))

    if tudo:
        relatorio = {}
        print("Rotacao ignorada (--tudo) ..... %d consultas" % len(grupos))
    else:
        # o orcamento vale por DIA, nao por invocacao: rodar o script tres
        # vezes numa tarde nao pode gastar tres vezes o teto e esvaziar o mes
        gasto_hoje = db.unidades_malha_hoje(con, malha.UNIDADES_POR_CONSULTA)
        se_sobra = max(0, orcamento - gasto_hoje)
        if gasto_hoje:
            print("Ja gasto hoje ................. %d unidades (sobram %d)"
                  % (gasto_hoje, se_sobra))

        ultimas = db.checagens_de_malha(con)
        candidatos = [{"chave": chave, "dias": dias_por_chave.get(chave),
                       "ultima": ultimas.get(chave)} for chave, _ in grupos]

        # a carteira muda toda semana: as faixas se ajustam ao credito em vez de
        # ficarem fixas sobrando ou faltando
        faixas, diag = malha.ajustar_faixas(candidatos, orcamento)
        print("Faixas ....................... %s  (fator %.2f)" % (
            " / ".join("<=%s:%dd" % (l if l else "+", i) for l, i in faixas),
            diag["fator"]))
        if abs(diag["fator"] - 1.0) > 0.05:
            print("   carteira pede %.1f consultas/dia, orcamento paga %.1f"
                  % (diag["consultas_base"], diag["orcamento_consultas"]))
        if diag.get("estourou"):
            print("   ATENCAO: nem no intervalo maximo a carteira cabe no plano.")
            print("   Voos vao ficar sem conferencia. Considere subir o plano.")

        escolhidos, relatorio = malha.priorizar(
            candidatos, orcamento_unidades=se_sobra, faixas=faixas)
        ordem = {chave: i for i, chave in enumerate(escolhidos)}
        grupos = sorted([g for g in grupos if g[0] in ordem],
                        key=lambda g: ordem[g[0]])
        print("Acompanhados no CRM (<%d dias) %d" % (
            malha.DIAS_MIN, relatorio.get("acompanhado_no_crm", 0)))
        print("Ainda no prazo da rotacao ..... %d" % relatorio.get("ainda_no_prazo", 0))
        if relatorio.get("sem_orcamento"):
            print("Adiados por orcamento ......... %d" % relatorio["sem_orcamento"])

    if limite is not None:      # "is not None": --limite 0 quer dizer zero
        grupos = grupos[:limite]
    print("Vou consultar ................. %d  (%d unidades, orcamento %d)\n"
          % (len(grupos), len(grupos) * malha.UNIDADES_POR_CONSULTA, orcamento))

    if plano:
        for (numero, data), _ in grupos:
            print("   %-10s %s   embarque em %s dias" % (
                numero, data, dias_por_chave.get((numero, data), "?")))
        print("\n(--plano: nada foi consultado nem gravado)")
        con.close()
        return
    ok = alertas = falhas = 0
    sem_malha = []
    incertos = []
    nao_consultados = []

    interrompida = None
    try:
        for i, ((numero, data), voos_crm) in enumerate(grupos, 1):
            saldo = provedor.unidades_restantes
            if saldo is not None and saldo < RESERVA_UNIDADES:
                interrompida = ("cota chegou a %d unidades (piso %d). Parei para "
                                "sobrar saldo para os voos mais proximos."
                                % (saldo, RESERVA_UNIDADES))
                print("\n>>> %s" % interrompida)
                nao_consultados.extend(g[0] for g in grupos[i - 1:])
                break

            print("[%d/%d] %s  %s" % (i, len(grupos), numero, data))
            try:
                contratos, erro = provedor.voo(numero, data)
            except MalhaIndisponivel as e:
                print("\nERRO: %s" % e)
                interrompida = str(e)
                nao_consultados.extend(g[0] for g in grupos[i - 1:])
                break

            if erro:
                print("       falhou: %s" % erro)
                falhas += 1
                continue

            # a consulta foi paga: anota a data para a rotacao andar, mesmo que
            # a leitura nao renda nada. Sem isso o mesmo voo problematico seria
            # reconsultado todo dia e consumiria a cota inteira.
            if not seco:
                db.marcar_checagem_malha(con, numero, data)
                con.commit()

            leitura = malha.ler_resposta(contratos)
            if not leitura["encontrada"]:
                # nao e cancelamento: pode ser data fora da cobertura
                print("       %s" % leitura["motivo"])
                sem_malha.append((numero, data))
                continue

            segmento, motivo = malha.escolher(leitura, voos_crm[0])
            if segmento is None:
                print("       %s" % motivo)
                incertos.append((numero, data, motivo))
                continue

            achados = []
            for voo in voos_crm:
                achados += malha.achados_de_status(segmento, voo)

            pode, porque = malha.confiavel(segmento)

            if pode:
                # comparacao padrao do sistema: um segmento contra a leitura
                # ANTERIOR desta mesma fonte (observado_antes), nao contra o
                # CRM. Mesma regra de LATAM/GOL/AZUL - ver comparacao.comparar.
                # Tem de rodar ANTES do registrar_observacao logo abaixo, que
                # sobrescreveria a baseline.
                achados += comparacao.comparar(
                    {"segmentos": [segmento], "segmentos_nao_expandidos": 0},
                    voos_crm, observado_antes)
            else:
                print("       leitura parcial (%s) - so status explicito" % porque)
                incertos.append((numero, data, porque))

            # Registra o que a malha viu, inclusive quando bate com a leitura
            # anterior. Sem isso nao da para saber que ela discorda de um
            # portal que concordou - foi o caso do AD 4626 em 30/07/2026,
            # malha 20:20 x Azul 20:40, que virou alerta sozinho (ver
            # db.divergencias).
            if pode and not seco:
                for voo_id, partida, rota, situacao in \
                        comparacao.observacoes_da_leitura(
                            {"segmentos": [segmento]}, voos_crm):
                    db.registrar_observacao(con, voo_id, "malha",
                                            partida, rota, situacao)
                con.commit()

            relevantes = [a for a in achados if a["voo_crm"]]
            if relevantes:
                for a in relevantes:
                    print("       ALERTA [%s] %s" % (a["tipo"], a["detalhe"][:70]))
                    if not seco:
                        db._registrar(con, a["voo_crm"]["id"], "alterado",
                                      "malha", a["tipo"], None, a["detalhe"])
                    alertas += 1
                if not seco:
                    con.commit()
            else:
                print("       OK - %s %s, %s" % (
                    segmento.get("origem") or "?", segmento.get("destino") or "?",
                    segmento.get("partida") or "sem horario"))
                ok += 1
        # o saldo do fornecedor e o que planeja a proxima rodada
        if provedor.unidades_restantes is not None:
            reset_em = None
            dias_reset = provedor.dias_para_reset()
            if dias_reset:
                reset_em = (datetime.now() + timedelta(days=dias_reset)).isoformat(
                    timespec="seconds")
            db.salvar_cota_malha(con, provedor.unidades_restantes,
                                 provedor.unidades_limite, reset_em)
            con.commit()
    finally:
        con.close()

    print("\n" + "=" * 62)
    print("  RESULTADO DA CHECAGEM PELA MALHA")
    print("=" * 62)
    # chamadas != unidades: retentativa de 429 conta como chamada HTTP e nao e
    # cobrada. Quem diz a verdade sobre custo e o saldo do fornecedor.
    print("  chamadas HTTP ............... %d" % provedor.chamadas)
    if provedor.unidades_restantes is not None:
        print("  cota restante ............... %d de %s unidades" % (
            provedor.unidades_restantes, provedor.unidades_limite or "?"))
    print("  conferidos sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d%s" % (alertas, " (SECO, nao gravado)" if seco else ""))
    print("  sem malha publicada ......... %d" % len(sem_malha))
    print("  leitura parcial ............. %d" % len(incertos))
    print("  falharam .................... %d" % falhas)
    if nao_consultados:
        print("  nao consultados ............. %d" % len(nao_consultados))
    print("=" * 62)

    if interrompida:
        print("\n  RODADA INTERROMPIDA: %s" % interrompida)
        print("  %d voo(s) ficaram sem conferencia por esta fonte." % len(nao_consultados))

    if sem_malha:
        print("\n  'Sem malha publicada' NAO quer dizer cancelado - a data pode")
        print("  estar fora da cobertura do plano. Esses voos seguem sem")
        print("  verificacao por esta fonte:")
        for numero, data in sem_malha[:10]:
            print("      %-10s %s" % (numero, data))
        if len(sem_malha) > 10:
            print("      ... e outros %d" % (len(sem_malha) - 10))

    # Rodada parcial (--limite) ou seca (--seco) nao representa o dia
    # cumprido - o vigia (src/vigia.py) tem de tentar de novo, cheio, depois.
    if limite is None and not seco:
        agenda.marcar(agenda.MALHA)


if __name__ == "__main__":
    main()
