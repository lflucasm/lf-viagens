"""Relatorio de gestao da LF Viagens - substitui o MCP pago da Volly.

Junta volly.py (leitura direta no Supabase deles) + gestao.py (contas em
Python) num pulso periodico: manda um resumo no Telegram e grava o
snapshot completo (JSON) no Supabase do PAINEL - pra uma pagina web ler
depois sem precisar recalcular nem gastar credito nenhum.

Uso:
    python3 src/relatorio_gestao.py --plano      # so imprime, nao envia/grava
    python3 src/relatorio_gestao.py              # envia Telegram + grava painel
    python3 src/relatorio_gestao.py --dias 30    # janela do "pulso da semana"
"""

import argparse
import datetime as _dt
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config
from volly import Volly
from volly_chat import VollyChat, ErroVollyChat
import gestao as g
import gestao_chat as gc
import alertas
import supabase_rest


def _brl(v):
    s = "%.2f" % abs(v)
    inteiro, dec = s.split(".")
    inteiro = "{:,}".format(int(inteiro)).replace(",", ".")
    sinal = "-" if v < 0 else ""
    return "%sR$ %s,%s" % (sinal, inteiro, dec)


def _pegar_tudo(v):
    """Uma chamada por tabela - o robo inteiro roda em ~15 requisicoes,
    contra 1 credito por chamada que o MCP cobrava (e cobrava por consulta
    JA AGREGADA, entao um relatorio como este custava dezenas de creditos)."""
    return {
        "emissoes": v.emissoes(),
        "clientes": v.clientes(),
        "transacoes": v.transacoes(),
        "contas": v.contas(),
        "categorias": v.categorias(),
        "fornecedores": v.fornecedores(),
        "milhas_contas": v.milhas_contas(),
        "funis": v.crm_funis(),
        "colunas": v.crm_colunas(),
        "cotacoes": v.crm_cotacoes(),
        "placements": v.crm_placements(),
        "followups": v.crm_followups(),
        "notas": v.nfse(),
        "perfis": v.equipe_perfis(),
        "tarefas": v.equipe_tarefas(),
    }


def _pegar_chat(dias_janela):
    """Best-effort: o chat roda num backend separado e federado por SSO
    (ver volly_chat.py) - se o refresh_token morreu, o resto do relatorio
    nao pode travar por causa disso. Devolve None quando falha."""
    try:
        vc = VollyChat(config)
        conversas_abertas = vc.conversas(so_abertas=True)
        _, mensagens = vc.mensagens_recentes(dias=dias_janela)
        protocolos = vc.protocolos()
        return {
            "conversas_abertas": conversas_abertas,
            "mensagens_recentes": mensagens,
            "protocolos": protocolos,
        }
    except ErroVollyChat as e:
        print("aviso: chat indisponivel (%s) - relatorio segue sem essa secao" % e)
        return None


def montar_snapshot(dados, dias_janela=7, hoje=None, dados_chat=None):
    """Todos os KPIs num dict so - isto e o que vira JSON pro painel web."""
    hoje = hoje or _dt.date.today()
    ini_ano = "%04d-01-01" % hoje.year
    fim = hoje.isoformat()
    ini_janela = (hoje - _dt.timedelta(days=dias_janela)).isoformat()

    emiss = dados["emissoes"]
    emiss_ytd = [e for e in emiss if (e.get("emission_date") or "") >= ini_ano]
    emiss_janela = [e for e in emiss if (e.get("emission_date") or "") >= ini_janela]
    tx = dados["transacoes"]

    ag_clientes = g.clientes_agregado(dados["clientes"], emiss, hoje)

    chat = {}
    if dados_chat:
        chat = {
            "chat_nao_respondidas": gc.nao_respondidas(
                dados_chat["conversas_abertas"], minutos=30, agora=None)[:15],
            "chat_tempo_resposta": gc.tempo_resposta(dados_chat["mensagens_recentes"]),
            "chat_volume_por_dia": gc.volume_por_dia(dados_chat["mensagens_recentes"]),
            "chat_protocolos_abertos": gc.protocolos_abertos(dados_chat["protocolos"])[:10],
        }

    return {
        "gerado_em": hoje.isoformat(),
        "janela_dias": dias_janela,
        "emissoes_ytd": g.resumo_emissoes(emiss_ytd),
        "emissoes_janela": g.resumo_emissoes(emiss_janela),
        "emissoes_por_mes": g.emissoes_por_mes(emiss_ytd),
        "ranking": g.ranking_emissores(emiss_ytd, dados["perfis"]),
        "financeiro_ytd": g.financeiro_resumo(tx, ini_ano, fim),
        "dre_ytd": g.dre(tx, dados["categorias"], ini_ano, fim),
        "vencidos": g.vencidos(tx)[:20],
        "vencidos_total": len(g.vencidos(tx)),
        "vencidos_soma": sum(x["valor"] for x in g.vencidos(tx)),
        "a_vencer_30d": g.a_vencer(tx, 30),
        "fornecedores_saldo": g.fornecedores_saldo(tx, dados["fornecedores"])[:10],
        "clientes_ativos": len(ag_clientes),
        "clientes_ltv_top": g.ltv(ag_clientes, "lucro_gerado", 10),
        "clientes_segmentos": {k: len(v) for k, v in
                               g.segmentar_clientes(ag_clientes).items()},
        "clientes_high_potential": g.segmentar_clientes(ag_clientes).get(
            "high_potential", [])[:10],
        "clientes_at_risk": g.segmentar_clientes(ag_clientes).get(
            "at_risk", [])[:10],
        "aniversariantes_30d": g.aniversariantes(dados["clientes"], ag_clientes, 30, hoje),
        "milhas_por_programa": g.milhas_resumo(dados["milhas_contas"]),
        "clubes_ativos": g.clubes_ativos(dados["milhas_contas"]),
        "clubes_custo_mensal": sum(c["custo_mensal"] for c in
                                   g.clubes_ativos(dados["milhas_contas"])),
        "clubes_alerta": g.clubes_alerta(dados["milhas_contas"]),
        "milhas_ociosas": g.milhas_ociosas(dados["milhas_contas"]),
        "crm_conversao": g.crm_conversao(dados["cotacoes"], dados["colunas"],
                                         dados["placements"], dados["funis"]),
        "crm_valor_por_etapa": g.crm_valor_por_etapa(
            dados["colunas"], dados["placements"], dados["cotacoes"], dados["funis"]),
        "crm_followups_atrasados": g.crm_followups_atrasados(
            dados["followups"], dados["cotacoes"]),
        "crm_perdidos_top": g.crm_perdidos(
            dados["cotacoes"], dados["colunas"], dados["placements"], dados["funis"]),
        "nfse_ytd": g.nfse_conformidade(emiss, dados["notas"], ini_ano, fim),
        "nfse_30d": g.nfse_conformidade(emiss, dados["notas"], ini_janela, fim),
        "tarefas_atrasadas": g.tarefas_atrasadas(dados["tarefas"], dados["perfis"]),
        **chat,
    }


def formatar_telegram(s):
    """Pulso curto pro Telegram (limite de 4000 chars) - numero primeiro,
    prioridade em destaque, sem enfeite. O snapshot completo fica no painel."""
    L = []
    L.append("📊 <b>LF Viagens — pulso de gestão</b> (%s)" % s["gerado_em"])
    L.append("")

    e = s["emissoes_janela"]
    L.append("✈️ <b>Últimos %dd:</b> %d emissões · %s vendido · %s lucro (%.1f%%)" % (
        s["janela_dias"], e["quantidade"], _brl(e["vendas_total"]),
        _brl(e["lucro_total"]), e["margem_pct"]))

    fr = s["financeiro_ytd"]
    L.append("💰 <b>Financeiro (ano):</b> recebido %s · a receber %s · pago %s · a pagar %s" % (
        _brl(fr["recebido"]), _brl(fr["a_receber"]), _brl(fr["pago"]), _brl(fr["a_pagar"])))
    if s["vencidos_total"]:
        L.append("   ⚠️ <b>%d vencidos</b> somando %s" % (
            s["vencidos_total"], _brl(s["vencidos_soma"])))

    for nome, r in s["crm_conversao"].items():
        if r["total"] == 0:
            continue
        L.append("🎯 <b>%s:</b> %d cotações · conversão %.1f%% · %s ganho" % (
            nome, r["total"], r["conversao_pct"], _brl(r["valor_ganho"])))

    if s["crm_followups_atrasados"]:
        top = s["crm_followups_atrasados"][0]
        L.append("📞 <b>%d follow-ups atrasados</b> (pior: %s — %s, %dd)" % (
            len(s["crm_followups_atrasados"]), top["cliente"] or "?",
            _brl(top["valor"]), top["dias_atraso"]))

    nfse = s["nfse_30d"]
    if nfse["faltantes"]:
        L.append("🧾 NFS-e (30d): %.0f%% conformidade — %d faltando" % (
            nfse["conformidade_pct"], nfse["faltantes"]))

    if s["clubes_alerta"]:
        L.append("🎫 %d clube(s) de milhas pra decidir renovação" % len(s["clubes_alerta"]))

    if s["tarefas_atrasadas"]:
        L.append("✅ %d tarefa(s) atrasada(s)" % len(s["tarefas_atrasadas"]))

    if s["aniversariantes_30d"]:
        nomes = ", ".join(a["cliente"] for a in s["aniversariantes_30d"][:5])
        L.append("🎂 Aniversário em 30d: %s" % nomes)

    if "chat_nao_respondidas" in s:
        nr = s["chat_nao_respondidas"]
        if nr:
            pior = nr[0]
            L.append("💬 <b>%d conversa(s) sem resposta</b> (pior: %s, %.0fh)" % (
                len(nr), pior["contato"], pior["esperando_segundos"] / 3600))
        tr = s["chat_tempo_resposta"]
        if tr["qtd_respostas"]:
            L.append("   1ª resposta média (7d): %.0f min · %d fora do SLA (30min)" % (
                tr["media_segundos"] / 60, len(tr["violacoes_sla"])))
        if s["chat_protocolos_abertos"]:
            L.append("   %d protocolo(s) aberto(s) 3+ dias" % len(s["chat_protocolos_abertos"]))

    if s["clientes_high_potential"]:
        top = s["clientes_high_potential"][0]
        L.append("💎 Recompra: %d cliente(s) 'high potential' parado(s) — "
                 "maior: %s (%s, 1x)" % (
                     len(s["clientes_high_potential"]), top["cliente"],
                     _brl(top["total_comprado"])))

    return "\n".join(L)


def gravar_painel(snapshot):
    """POST em gestao_relatorios (append-only - historico de pulsos, nao so
    o ultimo). Precisa da migration nova - ver
    supabase/migrations/*_gestao_relatorios.sql."""
    if not config.supabase_web_url or not config.supabase_web_service_key:
        return False, "SUPABASE_WEB_URL/SERVICE_KEY nao configurados"
    try:
        supabase_rest.inserir(
            config.supabase_web_url, config.supabase_web_service_key,
            "gestao_relatorios",
            {"gerado_em": snapshot["gerado_em"], "dados": snapshot},
        )
        return True, None
    except Exception as e:
        return False, str(e)[:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7, help="janela do pulso (default 7)")
    ap.add_argument("--plano", action="store_true", help="so imprime, nao envia nem grava")
    args = ap.parse_args()

    v = Volly()
    print("baixando dados da Volly (leitura direta, sem MCP)...")
    dados = _pegar_tudo(v)

    print("baixando dados do VollyChat...")
    dados_chat = _pegar_chat(args.dias)

    snapshot = montar_snapshot(dados, dias_janela=args.dias, dados_chat=dados_chat)
    texto = formatar_telegram(snapshot)

    print(texto.replace("<b>", "").replace("</b>", ""))
    print("\n(tamanho: %d chars)" % len(texto))

    if args.plano:
        print("\n--plano: nada enviado, nada gravado.")
        return

    ok, erro = alertas.enviar_telegram(config.telegram_token, config.telegram_chat, texto)
    print("Telegram:", "OK" if ok else "FALHOU (%s)" % erro)

    ok, erro = gravar_painel(snapshot)
    print("Painel:", "OK" if ok else "FALHOU (%s)" % erro)


if __name__ == "__main__":
    main()
