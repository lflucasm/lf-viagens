"""Aplicar na Volly: grava no trecho (`reminders`) a correcao de uma proposta
de `propostas_volly` - a UNICA escrita do sistema de voos na Volly.
Liberada pelo proprietário em 27/09/2026, com duas travas:

  1. clique humano: so roda quando alguem clica "Aplicar na Volly" na
     proposta (site -> RPC pedir_aplicacao_volly -> aplicar-volly.yml);
  2. chave: sem a variavel APLICAR_VOLLY=real (GitHub Actions variable,
     ligada so com o ok do proprietário) tudo roda em SIMULACAO - faz todas as
     conferencias, monta exatamente o PATCH e so avisa "Aplicaria".

Receita copiada do proprio site da Volly (bundle lido em 27/09/2026, tela de
reagendar trecho): ao mudar a partida, recalcula `reminder_date` = partida
menos as horas do check-in do trecho (`checkin_notification`: 12h/24h/48h/
72h; none/no_checkin/outros = 0) e, se esse lembrete ainda nao passou,
rearma o WhatsApp (`notify_whatsapp=false`, `status='pending'`) - o cliente
recebe o lembrete de check-in no horario novo.

Diferenca proposital da receita da Volly (conferido com o proprietário em
27/09/2026): o site deles volta `status` pra 'pending' mesmo com o check-in
ja marcado como feito ('sent'). Aqui so rearma quem ainda esta 'pending' -
check-in feito ou lembrete ignorado ('dismissed') nao sao reabertos.

Nao mexe em dinheiro: `reminders` nao tem nenhum campo de valor, e nada no
site da Volly calcula valor a partir dele (fatura, perfil do cliente e
relatorios leem os valores de `emissions`; o trecho so descreve a rota).
Mesmo assim, como gatilho de banco da Volly nao da pra ver de fora, a
aplicacao tira um retrato financeiro da emissao (campos de valor de
`emissions` + `financial_transactions` dela) antes e depois do PATCH e
alerta em vermelho se qualquer coisa mudar.

So aceita trecho de voo (`flight_direction` outbound/return, sem
`miles_transaction_id`): lembrete financeiro de milhas nunca e tocado.

Antes de gravar confere que a Volly AINDA tem o valor "de" da proposta: se
alguem ja corrigiu (ou mexeu em outra coisa nesses campos), nao sobrescreve.
Depois de gravar, rele e confere que ficou o valor "para".

Risco conhecido (bundle 27/09/2026): ressincronizar a emissao pela cotacao
na Volly apaga e recria os trechos com o horario antigo da cotacao. A
ingestao confere as propostas aplicadas a cada rodada (correcoes_desfeitas)
e o supervisor avisa.

Uso:
    python3 src/aplicar_volly_cloud.py --proposta ID   # o clique + a fila toda
    python3 src/aplicar_volly_cloud.py                 # so a fila (cron)
    python3 src/aplicar_volly_cloud.py --plano         # nunca grava
"""

import html
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import batimento
import nuvem_comum
import qualidade
import supabase_rest
from checar_latam_cloud import MilhasFlowConfig, autenticar_volly
from milhasflow import MilhasFlow

ETAPA = "aplicar-volly"

# Campos que uma proposta pode mudar (proposta_volly.montar) - qualquer outro
# nome em `campos` e ignorado: o robo nunca grava campo que nao conhece.
CAMPOS_PERMITIDOS = ("departure_datetime", "arrival_datetime", "flight_number",
                     "departure_airport", "arrival_airport")
CAMPOS_DATA = ("departure_datetime", "arrival_datetime")

# Mesma tabela do site da Volly (tXr no bundle) pro lembrete de check-in.
HORAS_CHECKIN = {"none": 0, "12h": 12, "24h": 24, "48h": 48, "72h": 72}


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def modo_real(plano=False, ambiente=None):
    """Grava de verdade so com APLICAR_VOLLY=real e sem --plano."""
    ambiente = os.environ if ambiente is None else ambiente
    return (not plano) and (ambiente.get("APLICAR_VOLLY", "").strip().lower() == "real")


def _instante(valor):
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def iguais(campo, a, b):
    """Datas comparadas como instante (a Volly devolve '...+00:00' e a
    proposta pode ter outro formato); texto sem espaco/caixa."""
    if campo in CAMPOS_DATA:
        ia, ib = _instante(a), _instante(b)
        return ia is not None and ib is not None and ia == ib
    norm = lambda v: "".join((v or "").split()).upper()
    return norm(a) == norm(b)


CAMPOS_DE_ROTA = ("departure_airport", "arrival_airport", "flight_number")


def rota_sem_portal(proposta):
    """Motivo de recusa se a proposta muda rota/numero sem vir do portal
    (mesma regra de proposta_volly.montar - aqui como segunda trava pras
    propostas gravadas antes dela existir, ex.: TSTABX em 27/09/2026)."""
    campos = proposta.get("campos") or {}
    if any(c in campos for c in CAMPOS_DE_ROTA) and not str(proposta.get("fonte") or "").startswith("portal-"):
        return ("a proposta muda aeroporto/numero do voo sem vir do portal da cia "
                "(pode ser reacomodacao ou escala) - conferir no portal e ajustar a mao")
    return None


def pendentes_de_aplicar(propostas):
    """Propostas com clique em "Aplicar" ainda sem resultado posterior ao
    clique. E a fila: o GitHub cancela o disparo pendente quando entra outro
    no mesmo grupo (cliques seguidos em 27/09/2026 perderam 5 de 6), entao
    TODA rodada processa todos os pedidos em aberto, nao so o do disparo."""
    fila = []
    for p in propostas:
        if p.get("status") != "proposta" or not p.get("pedido_em"):
            continue
        em = (p.get("resultado") or {}).get("em")
        pedido, feito = _instante(p["pedido_em"]), _instante(em)
        if feito is None or (pedido and pedido > feito):
            fila.append(p)
    return sorted(fila, key=lambda p: p.get("pedido_em") or "")


def conferir_antes(reminder, campos):
    """[(campo, esperado, atual)] onde a Volly ja nao tem o valor "de"."""
    divergentes = []
    for campo, mudanca in campos.items():
        if campo not in CAMPOS_PERMITIDOS:
            continue
        if not iguais(campo, reminder.get(campo), mudanca.get("de")):
            divergentes.append((campo, mudanca.get("de"), reminder.get(campo)))
    return divergentes


def montar_patch(reminder, campos, agora=None):
    """O PATCH exato que o site da Volly faria (ver docstring do modulo)."""
    agora = agora or datetime.now(timezone.utc)
    patch = {c: m.get("para") for c, m in campos.items() if c in CAMPOS_PERMITIDOS}
    if "departure_datetime" in patch:
        partida = _instante(patch["departure_datetime"])
        horas = HORAS_CHECKIN.get(reminder.get("checkin_notification") or "none", 0)
        lembrete = partida - timedelta(hours=horas)
        patch["reminder_date"] = lembrete.isoformat()
        # so rearma lembrete ainda pendente: check-in feito ('sent') ou
        # ignorado ('dismissed') fica como a equipe deixou
        if lembrete > agora and (reminder.get("status") or "pending") == "pending":
            patch["notify_whatsapp"] = False
            patch["status"] = "pending"
    patch["updated_at"] = agora.isoformat()
    return patch


def conferir_depois(reminder_depois, campos):
    """[(campo, esperado, gravado)] que nao ficou como a proposta mandou."""
    return [(c, m.get("para"), reminder_depois.get(c)) for c, m in campos.items()
            if c in CAMPOS_PERMITIDOS and not iguais(c, reminder_depois.get(c), m.get("para"))]


DIRECOES_DE_VOO = ("outbound", "return")

# Campos de valor da emissao que o retrato compara (tudo que e dinheiro,
# status de pagamento ou milhas - lista lida da tabela real em 27/09/2026)
CAMPOS_FINANCEIROS_EMISSAO = (
    "sale_value", "total_cost", "profit", "profit_margin", "fare_value",
    "taxes_cost", "markup_value", "extra_profit", "miles_cost", "miles_quantity",
    "cost_per_thousand", "payment_status", "supplier_payment_status",
    "consolidator_payment_status", "client_savings", "other_costs",
    "card_fee_cost", "iof_cost", "baggage_cost", "seats_cost", "pet_cost",
    "wallet_amount_used", "additional_payments", "payment_schedule",
    "supplier_payment_schedule")


def trecho_aplicavel(reminder):
    """None se pode aplicar, ou o motivo de recusa."""
    if reminder.get("miles_transaction_id"):
        return "trecho ligado a transacao de milhas - nao e trecho de voo"
    if reminder.get("flight_direction") not in DIRECOES_DE_VOO:
        return "nao e trecho de voo (%s)" % (reminder.get("flight_direction") or "sem direcao")
    return None


def retrato_financeiro(mf, emission_id):
    """Tudo que e valor na emissao do trecho + os lancamentos dela."""
    if not emission_id:
        return {}
    emissoes = mf._buscar_tabela("emissions", {
        "select": ",".join(CAMPOS_FINANCEIROS_EMISSAO), "id": "eq." + emission_id})
    lancamentos = mf._buscar_tabela("financial_transactions", {
        "select": "id,amount,is_paid,type,transaction_date,competence_date,payment_date,updated_at",
        "emission_id": "eq." + emission_id, "order": "id"})
    return {"emissao": emissoes[0] if emissoes else None, "lancamentos": lancamentos}


def diferencas_financeiras(antes, depois):
    """[texto] do que mudou entre dois retratos (vazio = nada mudou)."""
    mudou = []
    e1, e2 = (antes or {}).get("emissao") or {}, (depois or {}).get("emissao") or {}
    for campo in CAMPOS_FINANCEIROS_EMISSAO:
        if e1.get(campo) != e2.get(campo):
            mudou.append("emissao.%s: %s -> %s" % (campo, e1.get(campo), e2.get(campo)))
    l1 = {l["id"]: l for l in (antes or {}).get("lancamentos") or []}
    l2 = {l["id"]: l for l in (depois or {}).get("lancamentos") or []}
    for lid in sorted(set(l1) | set(l2), key=str):
        if l1.get(lid) != l2.get(lid):
            mudou.append("lancamento %s mudou" % lid)
    return mudou


def correcoes_desfeitas(mf, supabase_url, service_key):
    """Propostas aplicadas cujo trecho na Volly ja nao tem o valor aplicado
    (emissao ressincronizada pela cotacao, edicao manual...). Chamado pela
    ingestao a cada rodada; o supervisor le do batimento dela."""
    aplicadas = supabase_rest.select(
        supabase_url, service_key, "propostas_volly",
        {"select": "id,voo_id,campos,mensagem", "status": "eq.aplicada"})
    desfeitas = []
    for p in aplicadas:
        reminder = mf.buscar_reminder(p["voo_id"])
        nomes = passageiros_do_voo(supabase_url, service_key, p["voo_id"], reminder)
        if reminder is None:
            desfeitas.append({"proposta_id": p["id"], "voo_id": p["voo_id"],
                              "motivo": "trecho apagado na Volly",
                              "mensagem": p.get("mensagem"), "passageiros": nomes})
            continue
        diferentes = conferir_depois(reminder, p.get("campos") or {})
        if diferentes:
            desfeitas.append({"proposta_id": p["id"], "voo_id": p["voo_id"],
                              "motivo": "; ".join("%s voltou a %s" % (c, g) for c, _, g in diferentes),
                              "mensagem": p.get("mensagem"), "passageiros": nomes})
    return desfeitas


def _resumo(proposta, passageiros=""):
    texto = html.escape((proposta.get("mensagem") or "").replace("✏️ Na Volly mudaria — ", ""))
    return texto + ("\n👤 %s" % html.escape(passageiros) if passageiros else "")


def passageiros_do_voo(supabase_url, service_key, voo_id, reminder=None):
    """Nomes pra mensagem: passageiros da emissao (painel) ou, sem eles, o
    passenger_name do trecho na Volly."""
    try:
        voos = supabase_rest.select(supabase_url, service_key, "voos",
                                    {"select": "passageiros", "id": "eq.%s" % voo_id})
    except Exception:
        voos = []
    nomes = qualidade.nomes_passageiros((voos[0] if voos else {}).get("passageiros"))
    return nomes or (reminder or {}).get("passenger_name") or ""


def aplicar_uma(mf, url, key, token, chat, proposta, real, b):
    """Confere e aplica (ou simula) UMA proposta. Devolve "aplicada",
    "simulada" ou "erro". Sempre grava `resultado` na proposta."""
    proposta_id = proposta["id"]
    link = "%s/reserva/%s" % (nuvem_comum.PAINEL_WEB_URL, proposta["voo_id"])
    campos = {c: m for c, m in (proposta.get("campos") or {}).items() if c in CAMPOS_PERMITIDOS}
    reminder = mf.buscar_reminder(proposta["voo_id"])
    nomes = passageiros_do_voo(url, key, proposta["voo_id"], reminder)
    agora = datetime.now(timezone.utc)
    resultado = {"em": agora.isoformat(), "simulado": not real}

    def gravar(extra=None):
        dados = {"resultado": resultado}
        dados.update(extra or {})
        supabase_rest.atualizar(url, key, "propostas_volly", {"id": "eq.%d" % proposta_id}, dados)

    if not campos:
        resultado["erro"] = "proposta sem campos aplicaveis"
    elif rota_sem_portal(proposta):
        resultado["erro"] = rota_sem_portal(proposta)
    elif reminder is None:
        resultado["erro"] = "trecho nao existe mais na Volly"
    elif trecho_aplicavel(reminder):
        resultado["erro"] = trecho_aplicavel(reminder)
    else:
        divergentes = conferir_antes(reminder, campos)
        if divergentes:
            resultado["erro"] = "a Volly mudou desde a proposta: " + "; ".join(
                "%s esperado %s, esta %s" % d for d in divergentes)
        else:
            patch = montar_patch(reminder, campos, agora)
            resultado["patch"] = patch
            resultado["antes"] = {c: reminder.get(c) for c in patch if c != "updated_at"}

    if "erro" in resultado:
        print("  #%d NAO aplicado: %s" % (proposta_id, resultado["erro"]))
        gravar()
        b.falhas += 1
        alertas.enviar_telegram(token, chat,
            "⚠️ <b>Não apliquei na Volly</b> — %s\n%s\n🖥️ <a href=\"%s\">ver no painel</a>"
            % (_resumo(proposta, nomes), html.escape(resultado["erro"]), html.escape(link, quote=True)))
        return "erro"

    print("  #%d PATCH reminders %s: %s" % (proposta_id, reminder["id"], resultado["patch"]))
    if not real:
        gravar()
        print("  (simulacao: nada gravado na Volly)")
        alertas.enviar_telegram(token, chat,
            "🧪 <b>Simulação — aplicaria na Volly</b>: %s\n<i>Nada foi gravado.</i>\n"
            "🖥️ <a href=\"%s\">ver no painel</a>"
            % (_resumo(proposta, nomes), html.escape(link, quote=True)))
        return "simulada"

    financeiro_antes = retrato_financeiro(mf, reminder.get("emission_id"))
    gravado = mf.atualizar_reminder(reminder["id"], resultado["patch"])
    depois = mf.buscar_reminder(reminder["id"]) or gravado
    resultado["depois"] = {c: depois.get(c) for c in resultado["antes"]}

    mudou = diferencas_financeiras(
        financeiro_antes, retrato_financeiro(mf, reminder.get("emission_id")))
    resultado["financeiro_intocado"] = not mudou
    if mudou:
        # nao desfaz sozinho (seria uma segunda escrita as cegas): trava a
        # proposta como erro e grita - alguem confere na Volly
        resultado["erro"] = "VALORES FINANCEIROS MUDARAM apos gravar: " + "; ".join(mudou[:8])
        b.falhas += 1
        b.detalhe["financeiro_mudou"] = True
        gravar()
        alertas.enviar_telegram(token, chat,
            "🔴 <b>ATENÇÃO: valores financeiros mudaram depois de aplicar na Volly</b> — %s\n%s\n"
            "Conferir a emissão na Volly agora.\n🖥️ <a href=\"%s\">ver no painel</a>"
            % (_resumo(proposta, nomes), html.escape(resultado["erro"]), html.escape(link, quote=True)))
        return "erro"
    errados = conferir_depois(depois, campos)
    if errados:
        resultado["erro"] = "gravou mas nao ficou igual: " + "; ".join(
            "%s esperado %s, ficou %s" % e for e in errados)
        b.falhas += 1
        gravar()
        alertas.enviar_telegram(token, chat,
            "⚠️ <b>Aplicação na Volly não conferiu</b> — %s\n%s\n🖥️ <a href=\"%s\">ver no painel</a>"
            % (_resumo(proposta, nomes), html.escape(resultado["erro"]), html.escape(link, quote=True)))
        return "erro"

    gravar({"status": "aplicada", "aplicado_em": agora.isoformat()})
    print("  #%d aplicado e conferido" % proposta_id)
    alertas.enviar_telegram(token, chat,
        "✅ <b>Aplicado na Volly</b> — %s\n🖥️ <a href=\"%s\">ver no painel</a>"
        % (_resumo(proposta, nomes), html.escape(link, quote=True)))
    return "aplicada"


def main():
    """Processa a FILA inteira de pedidos em aberto (ver pendentes_de_aplicar).
    `--proposta ID` (o clique que disparou) so garante que essa entra mesmo
    se o pedido ainda nao estiver visivel; sem ela, e a rodada de hora em
    hora que esvazia o que o GitHub cancelou."""
    proposta_id = None
    if "--proposta" in sys.argv:
        valor = sys.argv[sys.argv.index("--proposta") + 1]
        proposta_id = int(valor) if valor.isdigit() else None
    plano = "--plano" in sys.argv
    real = modo_real(plano)

    url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    abertas = supabase_rest.select(url, key, "propostas_volly",
                                   {"select": "*", "status": "eq.proposta", "order": "id"})
    fila = pendentes_de_aplicar(abertas)
    if proposta_id and not any(p["id"] == proposta_id for p in fila):
        fila += [p for p in abertas if p["id"] == proposta_id and p.get("pedido_em")]
    print("Modo %s - %d pedido(s) na fila: %s" % (
        "REAL" if real else "simulacao", len(fila), [p["id"] for p in fila]))
    if not fila:
        # sem batimento nem login na Volly: rodada vazia de hora em hora nao
        # gasta o refresh_token giratorio a toa
        return

    with batimento.rodada(url, key, ETAPA) as b:
        b.detalhe.update({"modo": "real" if real else "simulacao",
                          "propostas": [p["id"] for p in fila]})
        mf = MilhasFlow(MilhasFlowConfig())
        autenticar_volly(mf, b.detalhe)
        contagem = {}
        for proposta in fila:
            try:
                situacao = aplicar_uma(mf, url, key, token, chat, proposta, real, b)
            except Exception as erro:
                # uma proposta ruim nao trava a fila; a quebra vai pro Telegram
                situacao = "erro"
                b.falhas += 1
                print("  #%d quebrou: %s" % (proposta["id"], erro))
                nuvem_comum.avisar_quebra("A aplicação na Volly (proposta %d)" % proposta["id"], erro)
            contagem[situacao] = contagem.get(situacao, 0) + 1
        b.lidos = contagem.get("aplicada", 0) + contagem.get("simulada", 0)
        b.detalhe["resultado"] = contagem
        print("Resumo: %s" % contagem)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("A aplicação na Volly", erro)
        sys.exit(1)
