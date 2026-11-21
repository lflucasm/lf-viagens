"""Lista de voos do painel (tabela `voos`) direto da Volly, na nuvem.

Ate aqui essa tabela so era alimentada pelo Mac (rodada.py -> sync.py ->
sincronizar_web.py). Desde 15/09/2026 a rodada do Mac aborta no login
(captcha da Volly, sem o refresh_token compartilhado) e a tabela ficou
congelada em 14/09: em 26/09 81 dos 162 trechos futuros nem existiam no
painel - nenhum checador de nuvem (malha, LATAM, Volly) os via.

Aqui a mesma montagem do Mac (sync.montar_voos: reminders + emissions +
tags, trecho terrestre fora) roda no GitHub Actions, com o token
compartilhado, e faz upsert no painel. Quem chama e ingestao_cloud.py
(workflow ingestao.yml, a cada 2h, com batimento); checar_volly_cloud.py
ainda chama `sincronizar` ate a Fase 3 do fluxo na nuvem tirar isso de la.

Alem de espelhar, marca `voos.incompleto` (texto com o motivo) no trecho que
nao da pra checar: sem numero de voo, numero composto/invalido ("TAP58 +
TAP540", "15346244795") ou aeroporto de origem sem fuso conhecido. O trecho
continua ativo no painel (a equipe ve), mas os checadores pulam e o
supervisor lista. Antes de marcar, aprende da AeroDataBox (snapshots da
Volly) o fuso de aeroporto fora do mapa fixo - ver aprender_fusos.
"""

import re
from datetime import datetime, timezone

import fusos
import supabase_rest
import sync
import vouchers
from nuvem_comum import agora_utc

# Trava contra leitura parcial da Volly: se vier bem menos trecho do que ha
# ativo no painel, NAO desativa ninguem - melhor um voo velho ativo a mais
# do que o monitoramento inteiro apagado por um soluco da API.
FRACAO_MINIMA_PARA_DESATIVAR = 0.5

# Numero de voo checavel: prefixo de cia (2-3, IATA ou ICAO, pode ter
# digito como "G3") + 1 a 4 digitos. Pega os casos reais de 26/09/2026:
# "TP + TP1928" (conexao digitada com o primeiro numero faltando) e
# "15346244795" (o localizador/bilhete no campo errado). Conexao digitada num
# trecho so ("TAP58 + TAP540") vale pelo primeiro voo.
NUMERO_VOO_VALIDO = re.compile(r"^[A-Z0-9]{2,3}\s?\d{1,4}$")

PAGINA_PAINEL = 1000  # max-rows padrao do PostgREST


def numero_normalizado(numero):
    return re.sub(r"\s+", " ", (numero or "").strip().upper())


def motivos_incompleto(voo):
    """[(codigo, texto)] do que impede checar o trecho; lista vazia = completo.

    O codigo agrupa no batimento; o texto vai pra coluna `incompleto` (o
    supervisor e o site mostram). Usa o mapa de fusos ja carregado (fixo +
    aprendido) - chamar depois de carregar/aprender.
    """
    motivos = []
    numero = numero_normalizado(voo.get("numero_voo"))
    # conexao digitada num trecho so ("TP1930 + TP1928"): vale o primeiro voo,
    # que parte do aeroporto do trecho (ver comparacao._normaliza_voo)
    primeiro = numero.split("+")[0].strip()
    if not numero:
        motivos.append(("sem_numero", "sem número de voo"))
    elif not NUMERO_VOO_VALIDO.match(primeiro):
        motivos.append(("numero_invalido",
                        "número de voo composto ou inválido: %s" % voo.get("numero_voo").strip()))
    origem = (voo.get("origem") or "").strip().upper()
    if not fusos.tem_fuso(origem):
        motivos.append(("sem_fuso", "fuso desconhecido do aeroporto %s" % (origem or "?")))
    return motivos


def texto_incompleto(voo):
    """Valor da coluna `incompleto`: None quando o trecho e checavel (limpa
    marca antiga, ex.: fuso aprendido depois ou numero corrigido na Volly)."""
    motivos = motivos_incompleto(voo)
    return "; ".join(t for _, t in motivos) or None


def decidir_desativacao(ativos_antes, ids_hoje):
    """(ids a desativar, travou). Funcao pura - a trava dos 50% mora aqui.

    Trecho ativo no painel que nao veio da Volly vira inativo, a menos que a
    Volly tenha devolvido menos de FRACAO_MINIMA_PARA_DESATIVAR dos ativos:
    ai e leitura parcial e ninguem e desativado.
    """
    sumiram = set(ativos_antes) - set(ids_hoje)
    if not sumiram:
        return set(), False
    if len(set(ids_hoje)) >= FRACAO_MINIMA_PARA_DESATIVAR * len(set(ativos_antes)):
        return sumiram, False
    return set(), True


def eh_futuro(voo, agora=None):
    agora = agora or datetime.now(timezone.utc)
    embarque = voo.get("embarque") or ""
    try:
        momento = datetime.fromisoformat(embarque.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento > agora


def _ids_painel(supabase_url, service_key, filtros):
    """ids de `voos` paginando (supabase_rest.select para em 1000 linhas)."""
    ids = set()
    offset = 0
    while True:
        params = dict(filtros, select="id", order="id",
                      limit=str(PAGINA_PAINEL), offset=str(offset))
        lote = supabase_rest.select(supabase_url, service_key, "voos", params)
        ids.update(l["id"] for l in lote)
        if len(lote) < PAGINA_PAINEL:
            return ids
        offset += PAGINA_PAINEL


def aeroportos_sem_fuso(voos):
    """Aeroportos (origem e destino) dos trechos sem fuso fixo nem aprendido."""
    return sorted({(a or "").strip().upper()
                   for v in voos for a in (v.get("origem"), v.get("destino"))
                   if fusos.e_aeroporto(a) and not fusos.tem_fuso(a)})


def fusos_dos_snapshots(linhas, procurados):
    """{iata: timeZone} lido das linhas de flight_status_snapshots (cada linha
    com os aeroportos das pernas em p0/c0/p1/c1). So o que foi procurado e
    com fuso valido - nada de chute."""
    achados = {}
    for linha in linhas:
        for campo in ("p0", "c0", "p1", "c1"):
            aeroporto = linha.get(campo) or {}
            iata = (aeroporto.get("iata") or "").strip().upper()
            fuso = aeroporto.get("timeZone")
            if iata in procurados and iata not in achados and fusos.fuso_valido(fuso):
                achados[iata] = fuso
    return achados


def aprender_fusos(mf, supabase_url, service_key, voos, plano=False):
    """Busca na AeroDataBox (via snapshots da Volly) o fuso dos aeroportos
    fora dos mapas e grava em `fusos_aeroporto`. Devolve {iata: fuso}.

    `flight_status_snapshots` e o cache GLOBAL da Volly (todas as agencias,
    ~1.200 linhas em 26/09/2026), e o numero do nosso trecho muitas vezes nao
    serve pra buscar (composto, ICAO, vazio). Entao filtra no proprio
    PostgREST pelos aeroportos procurados nas duas primeiras pernas do `raw`
    e traz so esses objetos - uma requisicao pequena, sem baixar os `raw`
    inteiros. Aeroporto que ninguem monitorou fica sem fuso (e o trecho,
    incompleto). Em `plano`, aprende so em memoria.
    """
    procurados = aeroportos_sem_fuso(voos)
    if not procurados:
        return {}
    lista = ",".join(procurados)  # so IATA de 3 letras (e_aeroporto): seguro no filtro
    condicoes = ",".join(
        "raw->%d->%s->airport->>iata.in.(%s)" % (perna, lado, lista)
        for perna in (0, 1) for lado in ("departure", "arrival"))
    linhas = mf._buscar_tabela("flight_status_snapshots", {
        "select": "p0:raw->0->departure->airport,c0:raw->0->arrival->airport,"
                  "p1:raw->1->departure->airport,c1:raw->1->arrival->airport",
        "or": "(%s)" % condicoes,
    })
    achados = fusos_dos_snapshots(linhas, set(procurados))
    fusos.aprender(achados)
    if achados and not plano:
        agora = agora_utc()
        supabase_rest.upsert(supabase_url, service_key, "fusos_aeroporto",
                             [{"iata": i, "fuso": f, "visto_em": agora}
                              for i, f in sorted(achados.items())], "iata")
    return achados


def sincronizar_detalhado(mf, supabase_url, service_key, plano=False):
    """Espelha a Volly em `voos`. Devolve o resumo da rodada (dict).

    `plano`: le tudo (Volly e painel) e calcula o que faria, sem gravar nada.
    """
    # Todo trecho da Volly: com ou sem emissao vinculada, e sem o
    # ignorados.txt - ele listava reserva "sem PDF salvo" (29/07/2026), motivo
    # que so valia pro conector do Mac; malha e monitor Volly nao precisam de
    # PDF (decisao do proprietário em 26/09/2026: monitorar todos os voos).
    voos_api = mf.buscar_voos(so_com_emissao=False)
    emissoes_api = mf.buscar_emissoes()
    # Venda sem nome de passageiro: tenta o voucher em PDF anexado nela
    # (07/10/2026). Falha aqui nunca derruba a ingestao - o trecho so fica
    # com o passenger_name da Volly, como antes.
    try:
        nomes_voucher = vouchers.nomes_por_reserva(mf, voos_api, emissoes_api)
    except Exception as erro:
        print("AVISO: nomes dos vouchers indisponiveis nesta rodada (%s)" % erro)
        nomes_voucher = {}
    voos = sync.montar_voos(voos_api, emissoes_api, mf.buscar_tags(), ignorados=set(),
                            nomes_voucher=nomes_voucher)

    # Fusos antes dos incompletos: todo chamador (inclusive o monitor Volly,
    # enquanto ainda sincroniza) marca igual - senao um marcava "sem fuso" e o
    # outro limpava, a cada rodada.
    fusos.carregar_aprendidos(supabase_url, service_key)
    aprendidos = aprender_fusos(mf, supabase_url, service_key, voos, plano)

    # Horario da Volly -> UTC real (ver fusos.volly_para_utc). Depois dos
    # fusos carregados: aeroporto aprendido agora ja converte nesta rodada.
    # Todo o resto do sistema (fusos.texto_local, site) le `voos.embarque`
    # como UTC de verdade.
    for v in voos:
        v["embarque"] = fusos.volly_para_utc(v.get("embarque"), v.get("origem"))
        v["chegada"] = fusos.volly_para_utc(v.get("chegada"), v.get("destino"))

    agora_dt = datetime.now(timezone.utc)
    agora = agora_utc()
    linhas = []
    incompletos = []
    for v in voos:
        motivos = motivos_incompleto(v)
        linhas.append(dict(v, ativo=True, visto_em=agora,
                           incompleto="; ".join(t for _, t in motivos) or None))
        if motivos and eh_futuro(v, agora_dt):
            incompletos.append((v, motivos))

    ativos_antes = _ids_painel(supabase_url, service_key, {"ativo": "eq.true"})
    todos_antes = _ids_painel(supabase_url, service_key, {})
    ids_hoje = {v["id"] for v in voos}
    desativar, travou = decidir_desativacao(ativos_antes, ids_hoje)

    if not plano:
        for i in range(0, len(linhas), 200):
            supabase_rest.upsert(supabase_url, service_key, "voos", linhas[i:i + 200], "id")
        for voo_id in sorted(desativar):
            supabase_rest.atualizar(supabase_url, service_key, "voos",
                                    {"id": "eq.%s" % voo_id},
                                    {"ativo": False, "visto_em": agora})
    if travou:
        print("AVISO: Volly devolveu %d trechos contra %d ativos no painel - "
              "nao desativei ninguem (leitura parcial?)" % (len(ids_hoje), len(ativos_antes)))

    por_motivo = {}
    for _, motivos in incompletos:
        for codigo, _texto in motivos:
            por_motivo[codigo] = por_motivo.get(codigo, 0) + 1

    return {
        "gravados": len(linhas),
        "novos": sorted(ids_hoje - todos_antes),
        "desativados": sorted(desativar),
        "trava_50": travou,
        "futuros_ativos": sum(1 for v in voos if eh_futuro(v, agora_dt)),
        "incompletos": incompletos,
        "incompletos_por_motivo": por_motivo,
        "fusos_aprendidos": aprendidos,
        "sem_fuso": aeroportos_sem_fuso(voos),
    }


def sincronizar(mf, supabase_url, service_key):
    """Devolve (gravados, novos, desativados) - forma antiga, usada pelo
    checar_volly_cloud.py ate a Fase 3 tirar a sincronizacao de la."""
    r = sincronizar_detalhado(mf, supabase_url, service_key)
    return r["gravados"], len(r["novos"]), len(r["desativados"])
