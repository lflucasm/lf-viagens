"""Ingestao: espelha os voos da Volly na tabela `voos` do painel, 100% na
nuvem (workflow ingestao.yml, a cada 2h). Parte 1 do fluxo de
monitoramento na nuvem (spec 2026-09-26).

E a primeira etapa de tudo: malha, monitor Volly e portais so checam o que
esta em `voos`. Ate 26/09/2026 isso rodava escondido dentro do monitor Volly
(e antes, so no Mac - parado desde 15/09 no captcha, com a lista congelada
por 11 dias sem ninguem ver). Aqui vira etapa propria com batimento
`ingestao`, que o supervisor le: se ela parar ou a contagem de voos futuros
despencar, alguem fica sabendo.

O trabalho em si mora em sincronizar_voos_cloud.sincronizar_detalhado:
todos os reminders aereos (com ou sem emissao), upsert com ativo = true,
desativacao com trava dos 50%, fuso aprendido da AeroDataBox e marca de
`incompleto`. So LE da Volly - nunca escreve la.

Uso:
    python3 src/ingestao_cloud.py            # rodada real (grava no painel)
    python3 src/ingestao_cloud.py --plano    # mostra o que faria, sem gravar
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aplicar_volly_cloud
import batimento
import clubes_cloud
import turbo_cloud
import nuvem_comum
import sincronizar_voos_cloud
from checar_latam_cloud import MilhasFlowConfig
from milhasflow import MilhasFlow
from volly import Volly

ETAPA = "ingestao"
# o batimento guarda a lista pro supervisor/site; acima disso so a contagem
MAX_LISTA_DETALHE = 60


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def montar_detalhe(resumo):
    """jsonb do batimento a partir do resumo de sincronizar_detalhado."""
    return {
        "novos": len(resumo["novos"]),
        "desativados": len(resumo["desativados"]),
        "trava_50": resumo["trava_50"],
        "futuros_ativos": resumo["futuros_ativos"],
        "incompletos": len(resumo["incompletos"]),
        "incompletos_por_motivo": resumo["incompletos_por_motivo"],
        "incompletos_lista": [
            {"id": v["id"], "localizador": v.get("localizador"),
             "numero_voo": v.get("numero_voo"), "origem": v.get("origem"),
             "destino": v.get("destino"), "embarque": v.get("embarque"),
             "motivo": "; ".join(t for _, t in motivos)}
            for v, motivos in resumo["incompletos"][:MAX_LISTA_DETALHE]],
        "fusos_aprendidos": resumo["fusos_aprendidos"],
        "sem_fuso": resumo["sem_fuso"],
    }


def imprimir(resumo, plano):
    verbo = "seriam" if plano else "foram"
    print("\n" + "=" * 62)
    print("  trechos aereos lidos na Volly ... %d" % resumo["gravados"])
    print("  futuros (ativos) ................ %d" % resumo["futuros_ativos"])
    print("  novos no painel ................. %d" % len(resumo["novos"]))
    print("  desativados ..................... %d%s" % (
        len(resumo["desativados"]), "  (TRAVA DOS 50%: ninguem desativado)"
        if resumo["trava_50"] else ""))
    print("  futuros incompletos ............. %d %s" % (
        len(resumo["incompletos"]), resumo["incompletos_por_motivo"] or ""))
    for v, motivos in resumo["incompletos"]:
        print("    %-14s %-16s %s-%s %s  %s" % (
            v.get("localizador") or "?", v.get("numero_voo") or "-", v.get("origem"),
            v.get("destino"), (v.get("embarque") or "")[:16],
            "; ".join(t for _, t in motivos)))
    if resumo["fusos_aprendidos"]:
        print("  fusos aprendidos ................ %s" % resumo["fusos_aprendidos"])
    if resumo["sem_fuso"]:
        print("  aeroportos ainda sem fuso ....... %s" % ", ".join(resumo["sem_fuso"]))
    print("=" * 62)
    if plano:
        print("\n(--plano: nada foi gravado; os numeros acima %s o resultado)" % verbo)


def espelhar_clubes(mf, supabase_url, service_key, plano):
    """Clubes da Volly -> painel. Falha aqui nao derruba a ingestao de voos."""
    try:
        r = clubes_cloud.sincronizar(
            Volly(MilhasFlowConfig(), mf=mf), supabase_url, service_key,
            os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID"), plano=plano)
        print("  clubes espelhados ............ %(contas)d (eventos %(eventos)d, avisos %(avisados)d)" % r)
    except Exception as erro:
        print("AVISO: espelho de clubes falhou (%s)" % erro)
    try:
        r = turbo_cloud.sincronizar(Volly(MilhasFlowConfig(), mf=mf), supabase_url, service_key, plano=plano)
        print("  turbo espelhado .............. %(titulares)d titulares (%(com_clube)d com clube)" % r)
    except Exception as erro:
        print("AVISO: espelho do turbo falhou (%s)" % erro)


def main():
    plano = "--plano" in sys.argv
    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    mf = MilhasFlow(MilhasFlowConfig())

    if plano:
        # sem batimento: simulacao nao pode contar pro supervisor como
        # ingestao que rodou
        resumo = sincronizar_voos_cloud.sincronizar_detalhado(
            mf, supabase_url, service_key, plano=True)
        imprimir(resumo, plano)
        espelhar_clubes(mf, supabase_url, service_key, True)
        return

    with batimento.rodada(supabase_url, service_key, ETAPA) as b:
        resumo = sincronizar_voos_cloud.sincronizar_detalhado(mf, supabase_url, service_key)
        b.lidos = resumo["gravados"]
        b.detalhe = montar_detalhe(resumo)
        # Correcao aplicada na Volly que voltou ao valor antigo (emissao
        # ressincronizada pela cotacao apaga e recria os trechos - ver
        # aplicar_volly_cloud.py). O supervisor le daqui e avisa.
        try:
            b.detalhe["correcoes_desfeitas"] = aplicar_volly_cloud.correcoes_desfeitas(
                mf, supabase_url, service_key)
        except Exception as erro:
            print("AVISO: conferencia de correcoes aplicadas falhou (%s)" % erro)
        if b.detalhe.get("correcoes_desfeitas"):
            print("  correcoes desfeitas na Volly .. %d" % len(b.detalhe["correcoes_desfeitas"]))
    imprimir(resumo, plano)
    espelhar_clubes(mf, supabase_url, service_key, False)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("A ingestão de voos (nuvem)", erro)
        sys.exit(1)
