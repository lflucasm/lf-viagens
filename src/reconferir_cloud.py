"""Reconferencia depois do "Verificado - passageiro avisado" (parte 4 do
spec do fluxo na nuvem, 26/09/2026).

O site marca o alerta como verificado (RPC marcar_historico_verificado) e
dispara reconferir.yml com o voo e o historico. Este script:

  1. le o trecho cadastrado na Volly (`reminders`, so leitura);
  2. le a companhia de novo, fora do intervalo de 10h do monitor:
       - portal da cia (LATAM/GOL/Azul), se houver - unica fonte que ve a
         reserva do passageiro (leitura_reserva.ler_reserva);
       - "Monitorar voo" da Volly com force=true (1 chamada da flight-status)
         e releitura do snapshot com a mesma filtragem de perna do monitor
         (leitura_do_dia / leitura_de_outro_dia / perna_da_venda);
       - ultima observacao da malha (so se recente) como ultimo recurso;
     prioridade da verdade: portal > Volly > malha;
  3. monta a proposta (proposta_volly.montar) e grava em `propostas_volly`;
  4. manda a proposta no Telegram com o link do painel;
  5. grava batimento `reconferencia` (o supervisor cobra proposta em ate
     10 min de cada verificado).

NUNCA escreve na Volly: nada de PATCH/POST em `reminders`. A proposta so
diz o que mudaria; o botao "Aplicar na Volly" e fase seguinte, depois que o
o proprietário validar as propostas. O `updated_at` do reminder e relido no fim pra
provar isso no log/batimento.

Uso:
    xvfb-run -a python3 src/reconferir_cloud.py --voo ID --historico ID
    python3 src/reconferir_cloud.py --voo ID --historico ID --plano
    python3 src/reconferir_cloud.py --voo ID --historico ID --plano --sem-portal

--plano: le tudo de verdade (inclusive a chamada a Volly), mas nao grava
proposta nem batimento; o Telegram sai marcado como simulacao.
--sem-portal: pula o portal da cia (teste local sem Chrome/Xvfb).
"""

import html
from datetime import datetime, timedelta, timezone
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import batimento
import checar_malha_cloud
import checar_volly_cloud
import fusos
import leitura_reserva
import nuvem_comum
import proposta_volly
import qualidade
import supabase_rest
from checar_latam_cloud import MilhasFlowConfig, autenticar_volly
from milhasflow import MilhasFlow

ETAPA = "reconferencia"
FONTE_VOLLY = checar_malha_cloud.ORIGEM_VOLLY
FONTE_MALHA = checar_malha_cloud.ORIGEM

# Snapshot da Volly mais velho que isso nao vale como "leitura nova" quando
# a chamada forcada falhou (voo noturno que a Volly nao acha, limite por
# hora): comparar a Volly com uma leitura de dias atras nao reconfere nada.
HORAS_SNAPSHOT_VALIDO = 12

# Observacao da malha so entra se for recente: em 26/09/2026 a TSTAEX tinha
# malha-cloud de 10 dias antes dizendo 09:00 (a grade velha) - usada como
# verdade, a proposta diria "Volly ja esta igual" com a companhia em 09:25.
HORAS_MALHA_VALIDA = 24

ROTULO_FONTE = {
    "portal-latam-cloud": "Portal LATAM",
    "portal-gol-cloud": "Portal GOL",
    "portal-azul-cloud": "Portal Azul",
    FONTE_VOLLY: "Monitor Volly",
    FONTE_MALHA: "Malha",
}


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def _argumento(nome):
    if nome not in sys.argv:
        return None
    indice = sys.argv.index(nome) + 1
    return sys.argv[indice] if indice < len(sys.argv) else None


def achar_reminder(mf, voo):
    """Reminder do trecho: pelo id (voos.id nasce do reminders.id) e, se o
    trecho foi recriado na Volly (id novo - visto com G3 2029 em 25/09/2026),
    pelo mesmo (numero, data local) que o monitor usa."""
    reminder = mf.buscar_reminder(voo["id"])
    if reminder:
        return reminder
    numero = checar_volly_cloud.numero_iata(voo.get("numero_voo"), voo.get("cia"))
    data = fusos.texto_local(voo.get("embarque"), voo.get("origem"))[:10]
    ids = checar_volly_cloud.reminders_por_chave(mf).get((numero, data)) or []
    return mf.buscar_reminder(ids[0]) if ids else None


def trecho_da_volly(reminder):
    """(numero IATA, data local, voo_crm) no formato que as funcoes de perna
    do monitor esperam - a partir do reminder, que e o que a proposta
    compara (hora da Volly lida com volly_para_utc, achado de 27/09/2026)."""
    origem = reminder.get("departure_airport")
    numero = checar_volly_cloud.numero_iata(reminder.get("flight_number"), reminder.get("airline"))
    local = fusos.texto_local(
        fusos.volly_para_utc(reminder.get("departure_datetime"), origem), origem)
    voo_crm = {"id": reminder["id"], "numero_voo": numero, "origem": origem,
               "destino": reminder.get("arrival_airport"), "embarque_local": local}
    return numero, (local or "")[:10], voo_crm


def leitura_volly(mf, reminder, numero, data, voo_crm, detalhe=None):
    """Forca o "Monitorar voo" (1 chamada) e rele o snapshot com a mesma
    filtragem de perna do monitor. Devolve (leitura, erro).

    `force: true` NAO garante leitura nova: em 27/09/2026 a TSTAEX/LA3588
    voltou com cache_hit=true e o snapshot de 19h antes (a Volly serve do
    cache dela, mesmo forcando, quando o voo foi consultado ha pouco - e
    essa consulta nao conta no teto de 120/h). Resposta `fromCache` vai no
    batimento (`volly_cache`, `volly_cache_de`) e na fonte da proposta
    ("Monitor Volly (cache de HH:MM)"), pra ninguem achar que a leitura e
    de agora - e e mais um motivo do portal vir antes.
    """
    resposta, erro = mf.consultar_status_voo(reminder["id"], forcar=True)
    cache = bool((resposta or {}).get("fromCache"))
    snaps = checar_volly_cloud.snapshots_por_numero(mf, [((numero, data), [voo_crm])])
    do_numero = snaps.get(numero)
    contratos, visto = checar_volly_cloud.leitura_do_dia(do_numero, data)
    if not contratos:
        contratos = checar_volly_cloud.leitura_de_outro_dia(do_numero, data)
        visto = do_numero[0].get("fetched_at") if (contratos and do_numero) else None
    if not contratos:
        return None, erro or "a Volly nao tem leitura desse voo"
    idade = checar_volly_cloud.idade_horas(visto)
    if detalhe is not None:
        if idade is not None:
            detalhe["idade_volly_h"] = round(idade, 1)
        detalhe["volly_cache"] = cache
        if cache:
            detalhe["volly_cache_de"] = visto
    if erro and (idade is None or idade > HORAS_SNAPSHOT_VALIDO):
        return None, "%s (snapshot de %s)" % (
            erro, "%.0fh atras" % idade if idade is not None else "idade desconhecida")
    contrato = checar_volly_cloud.perna_da_venda(contratos, voo_crm)[0]
    return proposta_volly.de_contrato_aerodatabox(contrato), erro


def fonte_volly(cache, fetched_at):
    """Fonte gravada na proposta quando a leitura e da Volly: o codigo da
    origem (o site traduz por ROTULO_ORIGEM) ou, se a Volly respondeu do
    cache dela, o rotulo com a hora do snapshot em Brasilia - ai o site
    mostra o texto como veio."""
    if not cache:
        return FONTE_VOLLY
    # instante_utc e nao fromisoformat: o fetched_at da Volly vem com fracao
    # de 2 digitos ("06:23:00.94+00:00"), que o Python 3.9 nao le
    momento = proposta_volly.instante_utc(fetched_at)
    if momento is None or fusos.ZoneInfo is None:
        return "Monitor Volly (cache)"
    local = momento.astimezone(fusos.ZoneInfo("America/Sao_Paulo"))
    return "Monitor Volly (cache de %s)" % local.strftime("%H:%M")


def leitura_malha(supabase_url, service_key, voo_id, numero, origem, destino):
    linhas = supabase_rest.select(
        supabase_url, service_key, "observacoes",
        {"select": "partida,rota,situacao,visto_em", "voo_id": "eq.%s" % voo_id,
         "origem": "eq.%s" % FONTE_MALHA})
    if not linhas:
        return None, "malha sem observacao desse voo"
    obs = linhas[0]
    idade = checar_volly_cloud.idade_horas(obs.get("visto_em"))
    if idade is None or idade > HORAS_MALHA_VALIDA:
        return None, "observacao da malha velha demais"
    return proposta_volly.de_observacao(obs, numero, origem, destino), None


def mensagem_telegram(voo, reminder, proposta, verificado_por, link, plano):
    cabeca = "🔁 <b>Reconferência%s — %s %s</b>" % (
        " (simulação)" if plano else "",
        html.escape(reminder.get("locator") or voo.get("localizador") or "?"),
        html.escape(reminder.get("flight_number") or voo.get("numero_voo") or "?"))
    nomes = qualidade.nomes_passageiros(voo.get("passageiros")) or reminder.get("passenger_name")
    linhas = [cabeca] + (["👤 %s" % html.escape(nomes)] if nomes else []) + [
              "", html.escape(proposta["mensagem"]), "",
              "Fonte: %s" % html.escape(ROTULO_FONTE.get(proposta.get("fonte"),
                                                         proposta.get("fonte") or "nenhuma"))]
    if verificado_por:
        linhas.append("Verificado por %s" % html.escape(verificado_por))
    if proposta["status"] == "proposta":
        linhas.append("<i>Nada foi alterado na Volly — é só a proposta.</i>")
    if link:
        linhas.append('<a href="%s">ver no painel</a>' % html.escape(link, quote=True))
    return "\n".join(linhas)


# Verificado ha mais que isso sem proposta nao entra mais na fila: a
# reconferencia de dias atras ja nao diz nada sobre o "agora" do clique
DIAS_FILA = 3


def verificados_sem_proposta(supabase_url, service_key, agora=None):
    """[(voo_id, historico_id)] verificados nos ultimos DIAS_FILA sem
    proposta criada depois do clique. E a fila: o GitHub cancela o disparo
    pendente quando entra outro no mesmo grupo milhasflow-auth (cliques
    seguidos em "Verificado" perdiam a reconferencia), entao toda rodada
    processa tudo que esta em aberto."""
    agora = agora or datetime.now(timezone.utc)
    desde = (agora - timedelta(days=DIAS_FILA)).isoformat(timespec="seconds")
    verificados = supabase_rest.select(supabase_url, service_key, "historico", {
        "select": "id,voo_id,verificado_em", "verificado_em": "gte.%s" % desde,
        "order": "verificado_em"})
    if not verificados:
        return []
    propostas = supabase_rest.select(supabase_url, service_key, "propostas_volly", {
        "select": "historico_id,criado_em", "criado_em": "gte.%s" % desde})
    return fila_sem_proposta(verificados, propostas)


def fila_sem_proposta(verificados, propostas):
    """Pura: verificados sem proposta posterior ao clique, sem repetir voo."""
    feitas = {}
    for p in propostas:
        if p.get("historico_id") is not None:
            feitas.setdefault(p["historico_id"], []).append(p.get("criado_em") or "")
    fila, vistos = [], set()
    for h in verificados:
        criadas = feitas.get(h["id"], [])
        if any(c >= (h.get("verificado_em") or "") for c in criadas):
            continue
        if h["voo_id"] in vistos:
            continue
        vistos.add(h["voo_id"])
        fila.append((h["voo_id"], h["id"]))
    return fila


def main():
    voo_id = _argumento("--voo")
    historico_id = _argumento("--historico")
    plano = "--plano" in sys.argv
    sem_portal = "--sem-portal" in sys.argv
    historico_id = int(historico_id) if (historico_id or "").isdigit() else None

    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")

    if "--contar" in sys.argv:
        # so o tamanho da fila (sem Volly): o workflow de hora em hora pula a
        # instalacao do Chrome quando nao ha nada pra reconferir
        print(len(verificados_sem_proposta(supabase_url, service_key)))
        return

    # o clique que disparou + tudo que ficou pra tras (disparo cancelado)
    fila = []
    if voo_id:
        fila.append((voo_id, historico_id))
    if not plano:
        fila += [(v, h) for v, h in verificados_sem_proposta(supabase_url, service_key)
                 if v not in {x for x, _ in fila}]
    print("Reconferencias na fila: %d" % len(fila))
    if not fila:
        return

    fusos.carregar_aprendidos(supabase_url, service_key)
    mf = MilhasFlow(MilhasFlowConfig())

    for voo, hist in fila:
        print("\n=== voo %s (historico %s)" % (voo, hist))
        if plano:
            # sem batimento: simulacao nao pode contar pro supervisor como
            # reconferencia feita (mesma regra do monitor Volly)
            b = batimento.Rodada()
            rodar(mf, supabase_url, service_key, b, voo, hist, plano, sem_portal)
            print("\nBatimento que seria gravado: lidos=%d falhas=%d\n%s" % (
                b.lidos, b.falhas, b.detalhe))
            continue
        try:
            with batimento.rodada(supabase_url, service_key, ETAPA) as b:
                rodar(mf, supabase_url, service_key, b, voo, hist, plano, sem_portal)
        except Exception as erro:
            # um voo ruim nao trava a fila (o batimento dele ja ficou ok=false)
            print("  quebrou: %s" % erro)
            nuvem_comum.avisar_quebra("A reconferência (voo %s)" % voo, erro)


def rodar(mf, supabase_url, service_key, b, voo_id, historico_id, plano, sem_portal):
    b.detalhe.update({"voo_id": voo_id, "historico_id": historico_id})

    voos = supabase_rest.select(supabase_url, service_key, "voos",
                                {"select": "*", "id": "eq.%s" % voo_id})
    if not voos:
        raise RuntimeError("voo %s nao existe no painel" % voo_id)
    voo = voos[0]

    verificado_por = None
    if historico_id is not None:
        hist = supabase_rest.select(
            supabase_url, service_key, "historico",
            {"select": "voo_id,verificado_por", "id": "eq.%s" % historico_id})
        if not hist:
            print("AVISO: historico %s nao existe - segue sem vincular" % historico_id)
            historico_id = None
        elif hist[0]["voo_id"] != voo_id:
            print("AVISO: historico %s e de outro voo (%s)" % (historico_id, hist[0]["voo_id"]))
        elif hist[0].get("verificado_por"):
            perfil = supabase_rest.select(
                supabase_url, service_key, "perfis",
                {"select": "nome", "id": "eq.%s" % hist[0]["verificado_por"]})
            verificado_por = perfil[0]["nome"] if perfil else None

    autenticar_volly(mf, b.detalhe)

    reminder = achar_reminder(mf, voo)
    if not reminder:
        proposta = {"status": "sem_proposta", "campos": {}, "fonte": None,
                    "mensagem": "⚠️ Sem proposta: trecho não encontrado na Volly. "
                                "Conferir no portal da cia."}
        leituras = {}
    else:
        b.detalhe["updated_at_volly"] = reminder.get("updated_at")
        numero, data, voo_crm = trecho_da_volly(reminder)
        print("Volly: %s %s %s %s-%s  partida %s (local)" % (
            reminder.get("locator"), numero, data, voo_crm["origem"], voo_crm["destino"],
            voo_crm["embarque_local"]))

        # fonte -> (leitura, erro), na ordem de prioridade
        leituras = {}
        cia = (voo.get("cia") or reminder.get("airline") or "").upper()
        if leitura_reserva.tem_portal(cia):
            fonte = leitura_reserva.FONTE[cia]
            if sem_portal:
                leituras[fonte] = (None, "pulado (--sem-portal)")
            else:
                bruta, erro = leitura_reserva.ler_reserva(
                    cia, voo.get("localizador") or reminder.get("locator"), voo, mf,
                    supabase_url, service_key)
                lida = proposta_volly.de_leitura_portal(
                    bruta, numero, data, voo_crm["origem"], voo_crm["destino"]) if bruta else None
                if bruta and not lida:
                    erro = "o portal nao mostra esse trecho"
                leituras[fonte] = (lida, erro)
        leituras[FONTE_VOLLY] = leitura_volly(mf, reminder, numero, data, voo_crm, b.detalhe)
        leituras[FONTE_MALHA] = leitura_malha(
            supabase_url, service_key, voo_id, numero, voo_crm["origem"], voo_crm["destino"])

        for fonte, (lida, erro) in leituras.items():
            print("  %-20s %s" % (fonte, lida if lida else "sem leitura: %s" % erro))

        fonte_escolhida, leitura = next(
            ((f, l) for f, (l, _) in leituras.items() if l), (None, None))
        if fonte_escolhida == FONTE_VOLLY:
            fonte_escolhida = fonte_volly(b.detalhe.get("volly_cache"),
                                          b.detalhe.get("volly_cache_de"))
        proposta = proposta_volly.montar(reminder, leitura, fonte_escolhida)

    b.lidos = 1 if proposta.get("fonte") else 0
    b.falhas = 0 if proposta.get("fonte") else 1
    b.detalhe.update({
        "status": proposta["status"], "fonte": proposta.get("fonte"),
        "erros": {f: e for f, (l, e) in leituras.items() if e},
    })

    print("\nProposta: %s (fonte %s)\n  %s" % (
        proposta["status"], proposta.get("fonte"), proposta["mensagem"]))
    if proposta["campos"]:
        for campo, de_para in proposta["campos"].items():
            print("    %-20s %s -> %s" % (campo, de_para["de"], de_para["para"]))

    if not plano:
        supabase_rest.inserir(supabase_url, service_key, "propostas_volly", {
            "voo_id": voo_id, "historico_id": historico_id,
            "status": proposta["status"], "campos": proposta["campos"],
            "fonte": proposta.get("fonte"), "mensagem": proposta["mensagem"],
        })

    link = alertas.link_painel(nuvem_comum.PAINEL_WEB_URL, voo_id)
    ok_envio, erro = alertas.enviar_telegram(
        os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
        mensagem_telegram(voo, reminder or {}, proposta, verificado_por, link, plano))
    print("\n>>> Telegram: %s" % ("enviado" if ok_envio else erro))

    # prova de que a Volly nao foi tocada (o script nao tem caminho de
    # escrita em reminders; isto so deixa registrado)
    if reminder:
        depois = mf.buscar_reminder(reminder["id"]) or {}
        intocada = depois.get("updated_at") == reminder.get("updated_at")
        b.detalhe["volly_intocada"] = intocada
        print(">>> reminders.updated_at %s: %s" % (
            "inalterado" if intocada else "MUDOU", depois.get("updated_at")))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("A reconferência (nuvem)", erro)
        sys.exit(1)
