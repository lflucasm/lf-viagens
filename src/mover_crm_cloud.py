"""Automacao do funil Pos-Venda do CRM (MilhasFlow/Volly), 100% na nuvem -
roda no GitHub Actions, sem Mac ligado. Move os cards de coluna baseado nos
dados de voo que o motor de checagem ja le do MilhasFlow; mover um card
dispara a mensagem de WhatsApp pre-configurada daquela coluna.

Mover um card NAO e um PATCH so - e uma receita de passos capturada ao
vivo (ver milhasflow.MilhasFlow.mover_cotacao_crm e a spec em
docs/superpowers/specs/2026-08-24-automacao-crm-milhasflow-design.md).
As regras de quando mover (dias pro embarque, nacional/internacional,
existencia de volta, timer de feedback) estao em crm_regras.py, sem
acesso a rede - testadas por testes/rodar_testes.py.

Toda rodada (--plano ou real) manda pro Telegram, dedup'ado desde o ultimo
aviso: (1) o que moveu/moveria agora, (2) o que vai mover nas proximas 24h
(planejar_futuro) - pra o proprietário nao ser pego de surpresa quando a
mensagem de WhatsApp sair pro cliente de verdade.

Uso:
    python3 src/mover_crm_cloud.py            # move de verdade
    python3 src/mover_crm_cloud.py --plano    # so mostra o que moveria
"""

import collections
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import crm_regras
import fusos
import nuvem_comum
import supabase_rest
from milhasflow import MilhasFlow


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


class MilhasFlowConfig(object):
    """Config minima pra reaproveitar MilhasFlow sem importar src/config.py
    inteiro (mesmo padrao de checar_latam_cloud.py)."""

    def __init__(self):
        self.email = _obrigatorio("MILHASFLOW_EMAIL")
        self.senha = _obrigatorio("MILHASFLOW_SENHA")
        self.anon_key = _obrigatorio("MILHASFLOW_ANON_KEY")
        self.organization_id = _obrigatorio("ORGANIZATION_ID")
        self.supabase_url = _obrigatorio("SUPABASE_URL").rstrip("/")
        self.caminho_tokens = "/tmp/milhasflow_tokens.json"
        # painel (milhasflow_auth_state) - deixa o refresh_token sobreviver
        # entre rodadas do Actions em vez de cair pro login por senha
        # (bloqueado por captcha desde 14/09/2026, ver milhasflow.py).
        self.supabase_web_url = os.environ.get("SUPABASE_WEB_URL", "").rstrip("/")
        self.supabase_web_service_key = os.environ.get("SUPABASE_WEB_SERVICE_KEY", "")


def trechos_por_locator(mf):
    """{locator: [trecho, ...]} no formato que crm_regras espera
    (origem/destino/embarque/chegada) - le direto de `reminders`, mesma
    fonte que o motor de checagem de voos ja usa.

    Por que por locator e nao por emission_id: testado em producao em
    24/08/2026 - as cotacoes do Pos-Venda sao copias da cotacao aprovada
    original (ver a spec), sem emissao nenhuma apontando pra elas. O
    localizador (presente tanto em `reminders.locator` quanto no `flights`
    da cotacao - ver crm_regras.locators_da_cotacao) e o unico jeito
    confiavel de casar card com voo de verdade.
    """
    por_locator = {}
    for v in mf.buscar_voos():
        locator = (v.get("locator") or "").strip().upper()
        if not locator:
            continue
        por_locator.setdefault(locator, []).append({
            "origem": v.get("departure_airport"),
            "destino": v.get("arrival_airport"),
            # UTC real: a Volly grava a hora local como se fosse de Brasilia
            # (ver fusos.volly_para_utc) - voo do exterior errava horas
            "embarque": fusos.volly_para_utc(v.get("departure_datetime"),
                                             v.get("departure_airport")),
            "chegada": fusos.volly_para_utc(v.get("arrival_datetime"),
                                            v.get("arrival_airport")),
        })
    return por_locator


def sincronizar_estagios(supabase_web_url, supabase_web_key, placements, estagios, agora):
    """Garante que `crm_estagios` reflita a coluna que a gente observa
    AGORA em cada card, mesmo pros que nunca passaram pela mao do robo.

    Sem isso, um card que chegou em Aguardando Feedback movido a mao (ou
    que ja estava la antes do robo existir) nunca teria `entrou_em`
    registrado - `calcular_estagio_alvo` devolveria None pra sempre e o
    card ficaria parado no timer de 2 dias eternamente (achado real na
    revisao de codigo, 24/08/2026). So atualiza quando a coluna observada
    diverge do que ja estava gravado - card que nao mudou de coluna nao
    tem `entrou_em` mexido, senao o timer nunca fecharia o ciclo.

    Muda `estagios` (dict) in-place e devolve a lista do que foi gravado -
    o chamador decide se grava de verdade (nao roda em --plano).
    """
    tocado_em = crm_regras.formatar_iso_z(agora)
    a_gravar = []
    for p in placements:
        quote_id = (p.get("quote") or {}).get("id")
        coluna_atual = p.get("column_key")
        if not quote_id or not coluna_atual:
            continue
        estado = estagios.get(quote_id)
        if estado and estado.get("estagio") == coluna_atual:
            continue
        registro = {"crm_quote_id": quote_id, "estagio": coluna_atual, "entrou_em": tocado_em}
        a_gravar.append(registro)
        estagios[quote_id] = registro
    return a_gravar


def planejar(placements, colunas, trechos_dos_locators, estagios, agora):
    """Devolve (planejadas, pendencias, erros_validacao) - nao acessa rede."""
    planejadas = []
    pendencias = []
    erros_validacao = []

    for p in placements:
        cotacao = p.get("quote") or {}
        quote_id = cotacao.get("id")
        if not quote_id:
            continue
        coluna_atual = p.get("column_key")
        nome = cotacao.get("client_name") or quote_id

        locators = crm_regras.locators_da_cotacao(cotacao)
        if not locators:
            pendencias.append((quote_id, nome, "sem localizador identificavel na cotacao (nao e viagem de aviao?)"))
            continue

        trechos = [t for loc in locators for t in (trechos_dos_locators.get(loc) or [])]
        if not trechos:
            # tinha localizador na cotacao mas nenhum trecho encontrado em
            # reminders. Card ja avancado no fluxo com o dado sumindo e
            # estranho o suficiente pra pedir olhar humano, nao so virar
            # pendencia calada.
            avancado = coluna_atual in (
                crm_regras.COL_CHECKUP_NACIONAL, crm_regras.COL_CHECKUP_INTERNACIONAL,
                crm_regras.COL_PROXIMA_NACIONAL, crm_regras.COL_PROXIMA_INTERNACIONAL,
                crm_regras.COL_EM_VIAGEM)
            (erros_validacao if avancado else pendencias).append(
                (quote_id, nome, "localizador(es) %s nao encontrado(s) nos voos monitorados"
                 % ", ".join(sorted(locators))))
            continue

        if (coluna_atual == crm_regras.COL_AGUARDANDO_VIAGEM
                and not crm_regras.tem_tag_onibus(cotacao.get("tags"))
                and crm_regras.embarque_ja_ocorreu(trechos, agora)
                and not crm_regras.viagem_ja_terminou(trechos, agora)):
            # embarcou mas a viagem ainda nao terminou - cliente pode estar
            # viajando agora. Ambiguo demais pro robo decidir sozinho (se a
            # viagem ja tivesse terminado de vez, calcular_estagio_alvo
            # abaixo ja fecha direto em Concluido sozinha). Nao vale pra
            # onibus: sem CheckUp/Viagem Proxima no caminho, achar o card
            # aqui logo apos o embarque e o ponto normal de transicao pra
            # Em Viagem/Aguardando Feedback, nao uma pendencia.
            erros_validacao.append(
                (quote_id, nome, "embarque ja ocorreu mas a viagem nao terminou e o card "
                       "ainda esta em Aguardando Viagem - confira manualmente"))
            continue

        estado = estagios.get(quote_id)
        entrou_em_feedback = None
        if estado and estado.get("estagio") == crm_regras.COL_AGUARDANDO_FEEDBACK:
            entrou_em_feedback = crm_regras.para_datetime(estado.get("entrou_em"))

        alvo = crm_regras.calcular_estagio_alvo(
            coluna_atual, trechos, entrou_em_feedback, agora, cotacao.get("tags"))
        if not alvo or alvo == coluna_atual:
            continue

        coluna_info = colunas.get(alvo) or {}
        template = coluna_info.get("whatsapp_message")
        if not template and alvo not in crm_regras.COLUNAS_SEM_MENSAGEM:
            # spec: mover sem mensagem configurada frustra o proposito
            # inteiro da automacao - fica pendente e avisa, nao move.
            pendencias.append((quote_id, nome, "coluna \"%s\" sem mensagem de WhatsApp configurada no Volly"
                               % (coluna_info.get("title") or alvo)))
            continue

        planejadas.append({
            "placement_id": p["id"], "quote_id": quote_id,
            "client_id": cotacao.get("client_id"), "client_name": nome,
            "titulo": cotacao.get("title") or "",
            "rota": crm_regras.resumo_rota(trechos),
            "coluna_de": coluna_atual, "coluna_para": alvo, "coluna_info": coluna_info,
        })

    return planejadas, pendencias, erros_validacao


def linha_movimento(item, colunas):
    """Linha de aviso do Telegram com o TITULO das colunas - o column_key das
    colunas criadas a mao no Volly e so `custom_<numero>`, ilegivel."""
    def nome(chave):
        return (colunas.get(chave) or {}).get("title") or chave
    return "- %s (%s) [%s]: %s → %s" % (
        item["client_name"], item.get("titulo") or "?", item.get("rota") or "?",
        nome(item["coluna_de"]), nome(item["coluna_para"]))


def planejar_futuro(placements, colunas, trechos_dos_locators, estagios, planejadas_hoje, agora,
                    dias_antecedencia=1):
    """O que o robo moveria daqui a `dias_antecedencia` dias se nada mudar
    ate la - pedido do proprietário (28/08/2026): com o modo real ligado, ele quer
    saber ANTES de uma movimentacao acontecer de verdade (card mudando de
    coluna + WhatsApp saindo pro cliente), nao só ficar sabendo depois.

    So devolve o que ainda NAO vai mover hoje (isso ja esta em
    `planejadas_hoje`, tratado e avisado a parte) mas entraria na janela
    de antecedencia - reusa `planejar` com um `agora` deslocado pro
    futuro. Pendencias/erros de validacao nao mudam com o tempo (nao
    dependem de `agora`), entao so a lista de movimentos importa aqui.
    """
    ids_hoje = {item["quote_id"] for item in planejadas_hoje}
    planejadas_futuras, _, _ = planejar(
        placements, colunas, trechos_dos_locators, estagios, agora + timedelta(days=dias_antecedencia))
    return [item for item in planejadas_futuras if item["quote_id"] not in ids_hoje]


def executar_movimentacao(mf, item, contagem_por_coluna, telefones, agora, brasilia):
    """`contagem_por_coluna`: collections.Counter mutado in-place - cada
    card movido incrementa a coluna de destino, pra dois cards indo pra
    mesma coluna na mesma rodada nao ganharem a mesma `position` (bug
    achado na revisao de codigo: uma foto tirada uma vez so no inicio da
    rodada nao acompanha os cards ja movidos DENTRO da propria rodada).
    `telefones`: {client_id: telefone} ja buscado em lote pelo chamador."""
    coluna_info = item["coluna_info"]
    nome = item["client_name"]
    tocado_em = crm_regras.formatar_iso_z(agora)
    posicao = contagem_por_coluna[item["coluna_para"]]

    if item["coluna_para"] in crm_regras.COLUNAS_SEM_MENSAGEM:
        # coluna terminal, sem mensagem configurada (nem deveria ter) - so
        # move o card e limpa agendamento pendente, sem tentar mandar nada.
        mf.mover_cotacao_crm(
            item["placement_id"], item["quote_id"], item["coluna_para"], posicao,
            None, None, None, None, None, tocado_em)
        contagem_por_coluna[item["coluna_para"]] += 1
        return True, tocado_em

    telefone = telefones.get(item["client_id"]) or ""
    if not telefone:
        return False, "cliente sem telefone cadastrado"

    mensagem = crm_regras.montar_mensagem(coluna_info.get("whatsapp_message"), nome)
    if not mensagem:
        return False, "mensagem da coluna tem placeholder que o robo nao sabe substituir"

    agendar_para = crm_regras.calcular_agendamento(
        agora, coluna_info.get("followup_days"), coluna_info.get("followup_time"), brasilia)
    if not agendar_para:
        return False, "coluna sem followup_days/followup_time configurado"

    mf.mover_cotacao_crm(
        item["placement_id"], item["quote_id"], item["coluna_para"], posicao,
        item["client_id"], telefone, "55", mensagem, agendar_para, tocado_em)
    contagem_por_coluna[item["coluna_para"]] += 1
    return True, tocado_em


def main():
    plano = "--plano" in sys.argv

    supabase_web_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    supabase_web_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    mf = MilhasFlow(MilhasFlowConfig())
    brasilia = ZoneInfo("America/Sao_Paulo") if ZoneInfo else timezone.utc
    agora = datetime.now(timezone.utc)

    colunas = {c["column_key"]: c for c in mf.buscar_colunas_crm()}
    placements = mf.buscar_cotacoes_crm()
    trechos_dos_locators = trechos_por_locator(mf)
    estagios = {e["crm_quote_id"]: e for e in supabase_rest.select(
        supabase_web_url, supabase_web_key, "crm_estagios", {"select": "*"})}
    avisos_anteriores = {a["crm_quote_id"]: a["aviso"] for a in supabase_rest.select(
        supabase_web_url, supabase_web_key, "crm_avisos_plano", {"select": "*"})}
    avisos_futuros_anteriores = {a["crm_quote_id"]: a["aviso"] for a in supabase_rest.select(
        supabase_web_url, supabase_web_key, "crm_avisos_futuro", {"select": "*"})}

    a_sincronizar = sincronizar_estagios(supabase_web_url, supabase_web_key, placements, estagios, agora)
    if a_sincronizar and not plano:
        supabase_rest.upsert(supabase_web_url, supabase_web_key, "crm_estagios",
                             a_sincronizar, "crm_quote_id")

    planejadas, pendencias, erros_validacao = planejar(
        placements, colunas, trechos_dos_locators, estagios, agora)
    # so avisa por Telegram o que mudou desde a ultima rodada - senao, como
    # --plano nunca escreve nada no board, o mesmo aviso seria reenviado a
    # cada 2h pra sempre (pedido do proprietário, 2026-08-28).
    planejadas_novas, pendencias_novas, erros_novos, avisos_atuais = crm_regras.selecionar_novidades(
        planejadas, pendencias, erros_validacao, avisos_anteriores)
    if avisos_atuais:
        supabase_rest.upsert(supabase_web_url, supabase_web_key, "crm_avisos_plano",
                             [{"crm_quote_id": qid, "aviso": av} for qid, av in avisos_atuais.items()],
                             "crm_quote_id")

    # aviso de "vai mover amanha" - pedido do proprietário: quer saber ANTES da
    # movimentacao de verdade acontecer, nao so depois. Roda em --plano e
    # em modo real igual (e so leitura + um aviso, nao mexe no board).
    planejadas_futuras = planejar_futuro(
        placements, colunas, trechos_dos_locators, estagios, planejadas, agora)
    futuras_novas, _, _, avisos_futuros_atuais = crm_regras.selecionar_novidades(
        planejadas_futuras, [], [], avisos_futuros_anteriores)
    if avisos_futuros_atuais:
        supabase_rest.upsert(supabase_web_url, supabase_web_key, "crm_avisos_futuro",
                             [{"crm_quote_id": qid, "aviso": av} for qid, av in avisos_futuros_atuais.items()],
                             "crm_quote_id")
    if futuras_novas:
        alertas.enviar_telegram(
            telegram_token, telegram_chat,
            "📅 <b>CRM: previstas para mover nas proximas 24h</b>\n\n"
            + "\n".join(linha_movimento(i, colunas) for i in futuras_novas[:20]))

    print("Cotacoes no funil Pos-Venda ....... %d" % len(placements))
    print("Moveriam de coluna ................ %d (novas: %d)" % (len(planejadas), len(planejadas_novas)))
    if pendencias:
        print("Pendencias (sem dado suficiente) .. %d (novas: %d)" % (len(pendencias), len(pendencias_novas)))
    if erros_validacao:
        print("Precisam de olhar humano ........... %d (novos: %d)" % (len(erros_validacao), len(erros_novos)))

    if plano:
        for item in planejadas:
            print("   %-30s %-25s [%s] %s -> %s" % (
                item["client_name"][:30], item.get("titulo", "")[:25], item.get("rota", ""),
                item["coluna_de"], item["coluna_para"]))
        for _, nome, motivo in pendencias:
            print("   pendencia: %-30s %s" % (nome[:30], motivo))
        for _, nome, motivo in erros_validacao:
            print("   olhar humano: %-30s %s" % (nome[:30], motivo))
        print("\n(--plano: nada foi movido, nenhuma mensagem foi agendada, nem crm_estagios foi gravado)")

        if planejadas_novas or pendencias_novas or erros_novos:
            partes = ["🔎 <b>CRM (simulacao): novidades desde o ultimo aviso</b>"]
            if planejadas_novas:
                partes.append("\n<b>Moveria:</b>\n" + "\n".join(
                    linha_movimento(i, colunas) for i in planejadas_novas[:20]))
            if erros_novos:
                partes.append("\n<b>Precisam de olhar humano:</b>\n" + "\n".join(
                    "- %s (%s)" % (n, m) for _, n, m in erros_novos[:20]))
            if pendencias_novas:
                partes.append("\n<b>Pendencias:</b>\n" + "\n".join(
                    "- %s (%s)" % (n, m) for _, n, m in pendencias_novas[:20]))
            alertas.enviar_telegram(telegram_token, telegram_chat, "\n".join(partes))
        return

    contagem_por_coluna = collections.Counter(p.get("column_key") for p in placements)
    ids_com_mensagem = {item["client_id"] for item in planejadas
                        if item["coluna_para"] not in crm_regras.COLUNAS_SEM_MENSAGEM
                        and item.get("client_id")}
    telefones = {cid: c.get("phone") for cid, c in mf.buscar_clientes_crm(ids_com_mensagem).items()}

    movidas = falhas = 0
    estagios_para_gravar = []
    falhas_execucao = []
    for item in planejadas:
        try:
            ok, detalhe = executar_movimentacao(
                mf, item, contagem_por_coluna, telefones, agora, brasilia)
        except Exception as e:
            ok, detalhe = False, str(e)[:150]

        if ok:
            estagios_para_gravar.append({"crm_quote_id": item["quote_id"],
                                         "estagio": item["coluna_para"], "entrou_em": detalhe})
            movidas += 1
            print("   movido: %s (%s -> %s)"
                  % (item["client_name"], item["coluna_de"], item["coluna_para"]))
        else:
            falhas += 1
            falhas_execucao.append((item["client_name"], detalhe))
            print("   ERRO movendo %s: %s" % (item["client_name"], detalhe))

    if estagios_para_gravar:
        supabase_rest.upsert(supabase_web_url, supabase_web_key, "crm_estagios",
                             estagios_para_gravar, "crm_quote_id")

    print("\n" + "=" * 62)
    print("  movidos ....................... %d" % movidas)
    print("  falharam ....................... %d" % falhas)
    print("=" * 62)

    if erros_novos:
        # ja deduplicado por selecionar_novidades - so avisa quando o
        # motivo mudou desde a ultima rodada, mesmo tratamento do --plano.
        alertas.enviar_telegram(
            telegram_token, telegram_chat,
            "⚠️ <b>CRM: cotacoes precisam de conferencia manual</b>\n\n"
            + "\n".join("- %s (%s)" % (n, m) for _, n, m in erros_novos[:20])
            + "\n\nEstavam avancadas no funil, mas o robo nao achou mais o "
              "trecho de voo ligado a emissao - confira se a venda mudou.")

    if falhas_execucao:
        # falha de execucao e sempre uma tentativa nova desta rodada - nao
        # passa pelo dedup de avisos (diferente de erros_validacao/
        # pendencias, que sao recalculados identicos rodada apos rodada).
        alertas.enviar_telegram(
            telegram_token, telegram_chat,
            "🚨 <b>CRM: %d movimentacao(oes) falharam</b>\n\n"
            % falhas
            + "\n".join("- %s: %s" % (n, m) for n, m in falhas_execucao)
            + "\n\nVeja o log do GitHub Actions pra mais detalhe.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("A automacao de CRM (Pos-Venda)", erro)
        sys.exit(1)
