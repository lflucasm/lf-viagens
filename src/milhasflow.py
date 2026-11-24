"""Cliente da API do MilhasFlow (Supabase / PostgREST).

O MilhasFlow expoe o backend Supabase direto para o navegador. Aqui a gente
autentica como o proprio usuario da agencia e consulta as mesmas tabelas que
a tela de "Acompanhamentos > Voos" consulta.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qualidade
import supabase_rest

PAGINA = 1000  # PostgREST limita a resposta; paginamos ate acabar

# Cabecalho de navegador comum (Chrome no Mac) nas chamadas a Volly, em vez
# do "LFViagens-ChecagemVoos" que identificava a automacao - pedido do proprietário
# em 28/09/2026, junto com o ritmo de pessoa do monitor (ritmo_humano.py).
# Vale pra tudo que fala com a Volly (este cliente e o do VollyChat).
USER_AGENT_NAVEGADOR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36")
MILHASFLOW_AUTH_ID = "lfviagens"  # linha fixa em milhasflow_auth_state (ver migration)

CAMPOS_VOO = (
    "id,emission_id,departure_airport,arrival_airport,departure_datetime,"
    "arrival_datetime,airline,flight_number,cabin_class,flight_direction,"
    "flight_group_index,flight_leg_order,locator,status,checkin_notification,"
    "checked_in_by,checked_in_at,passenger_name"
)

CAMPOS_EMISSAO = (
    "id,crm_quote_id,sale_value,localizador,emissor_id,"
    "client:clients(name),emissor:profiles(full_name),passengers_data"
)

# So os campos que checar_latam_cloud.py precisa pra montar o deep link sem
# PDF/iCloud - ver extrair_pedido_latam().
CAMPOS_LINK_LATAM = ("id,localizador,emission_link,ticket_file_url,passenger_name,"
                     "passengers_data,package_data")

# reminders guarda tambem eventos de hotel; queremos so o que voa
DIRECOES_IGNORADAS = ("checkin_hotel", "checkout_hotel")

# O numero de compra da LATAM (formato LA + digitos + letras, ex:
# LA9500002TEST) aparece tanto na query string do emission_link
# (?orderId=...) quanto no NOME do arquivo do ticket_file_url/CUV
# (bilhete_latam_LA9500002TEST_....pdf, LA9500001TEST-<uuid>-cuv.pdf) -
# por isso a extracao e por regex solta, nao por parse de query string.
RE_PEDIDO_LATAM = re.compile(r"\bLA\d{5,10}[A-Z]{2,8}\b")
RE_LASTNAME = re.compile(r"last[Nn]ame=([^&#\"\s\\]+)")

# Aba CRM (Pos-Venda) - descoberto na pratica em 24/08/2026 inspecionando o
# trafego de rede do proprio site (a introspecao automatica do schema, que
# funcionava ate pouco tempo atras, passou a exigir a chave service_role
# que nao temos - ver docs/superpowers/specs/2026-08-24-automacao-crm-
# milhasflow-plan.md, Fase 1). O board fica no funil "Pos-Venda":
POS_VENDA_FUNNEL_ID = "3206aaa9-8cf1-4b31-8aca-f1737a8c9ad8"

CAMPOS_COLUNA_CRM = "id,column_key,title,whatsapp_message,followup_days,followup_time"
# select igual ao que o proprio site usa pra carregar o board (capturado
# via DevTools) - embed de crm_quotes com o alias "quote" mesmo.
# NEM `crm_quotes.emission_id` NEM `emissions.crm_quote_id` servem de link
# pras cotacoes do Pos-Venda - testado em producao em 24/08/2026: as 42
# cotacoes do funil sao COPIAS da cotacao original aprovada (ver
# `notes.observations`, sempre "[Duplicado de Aprovado em ...]"), com id
# novo, sem nenhuma emissao apontando pra elas (interseccao = 0 num teste
# real). O jeito que funciona e casar por LOCALIZADOR: `flights` (JSON
# embutido na cotacao, contem os locators que o atendente digitou) contra
# `reminders.locator`, que crm_regras.locators_da_cotacao/mover_crm_cloud.
# trechos_por_locator fazem.
CAMPOS_PLACEMENT_CRM = "id,column_key,position,quote:crm_quotes!inner(id,client_id,client_name,title,tags,flights)"


def _primeiro_nome_passageiro(passageiros):
    """passengers_data vem em dois formatos: lista [{name}] (vendas antigas)
    ou {"flightGroups": [[{name, cpf, ...}]], ...} (vendas novas do CRM)."""
    if isinstance(passageiros, dict):
        grupos = passageiros.get("flightGroups") or []
        passageiros = [p for g in grupos if isinstance(g, list) for p in g]
    for p in passageiros or []:
        if isinstance(p, dict) and (p.get("name") or "").strip():
            return p["name"]
    return None


def extrair_pedido_latam(emissao):
    """Emissao (dict de buscar_links_latam) -> (orderId, lastname) ou
    (None, None) se nao tiver como montar o deep link.

    Prioridade: emission_link primeiro (mais provavel ter o sobrenome na
    query string tambem), ticket_file_url depois. Venda antiga sem PDF
    gerado pelo MilhasFlow nao tem nenhum dos dois - fica de fora ate ser
    reemitida ou o operador anexar o comprovante (ver conversa de
    12/08/2026: aceito ficar assim por ora, cobre a maioria das vendas).
    """
    pedido = None
    sobrenome = None
    # package_data (JSON da venda feita pelo CRM) guarda o "Nro compra" da aba
    # Vendas em flights.*[].purchaseNumber/reservationUrl - e a unica fonte de
    # vendas novas sem PDF anexado (ex.: TSTAHX, 16/10/2026). Entra por ultimo.
    package = emissao.get("package_data")
    campos = [emissao.get("emission_link"), emissao.get("ticket_file_url"),
              json.dumps(package) if package else None]
    for url in campos:
        url = url or ""
        if not url:
            continue
        achado = RE_PEDIDO_LATAM.search(url)
        if achado and not pedido:
            pedido = achado.group(0).upper()
        achado_nome = RE_LASTNAME.search(url)
        if achado_nome and not sobrenome:
            sobrenome = urllib.parse.unquote(achado_nome.group(1))
        if pedido and sobrenome:
            break

    if pedido and not sobrenome:
        # nenhum dos links trazia lastName na query (caso do CUV, que e so
        # um caminho de arquivo) - cai pro nome que o MilhasFlow ja tem.
        nome = emissao.get("passenger_name") or _primeiro_nome_passageiro(
            emissao.get("passengers_data"))
        sobrenome = qualidade.sobrenome(nome) or None

    if not pedido or not sobrenome:
        return None, None
    return pedido, sobrenome


class ErroMilhasFlow(Exception):
    pass


class MilhasFlow(object):
    def __init__(self, config):
        self.cfg = config
        self._access_token = None
        self._expira_em = 0

    # ------------------------------------------------------------------ HTTP

    def _requisitar(self, url, metodo="GET", corpo=None, cabecalhos=None, autenticado=True):
        headers = {
            "apikey": self.cfg.anon_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT_NAVEGADOR,
        }
        if autenticado:
            headers["Authorization"] = "Bearer " + self._token()
        if corpo is not None:
            headers["Content-Type"] = "application/json"
        if cabecalhos:
            headers.update(cabecalhos)

        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(url, data=dados, headers=headers, method=metodo)

        # 24/11/2026: HTTP 522 (Cloudflare) do Supabase do MilhasFlow derrubou
        # ingestao e CRM numa rodada. So GET (idempotente) tenta de novo.
        tentativas = 3 if metodo == "GET" else 1
        for n in range(tentativas):
            ultima = n == tentativas - 1
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    bruto = resp.read().decode("utf-8")
                    return json.loads(bruto) if bruto else None
            except urllib.error.HTTPError as e:
                if not ultima and (e.code >= 500 or e.code == 429):
                    time.sleep(3 * (n + 1))
                    continue
                detalhe = e.read().decode("utf-8", "replace")[:400]
                raise ErroMilhasFlow("HTTP %s em %s\n%s" % (e.code, url.split("?")[0], detalhe))
            except urllib.error.URLError as e:
                if not ultima:
                    time.sleep(3 * (n + 1))
                    continue
                raise ErroMilhasFlow("Falha de conexao: %s" % e.reason)

    # ------------------------------------------------------------------ Auth

    def _tem_painel(self):
        return bool(getattr(self.cfg, "supabase_web_url", None)
                    and getattr(self.cfg, "supabase_web_service_key", None))

    def _tokens_remotos(self):
        """`milhasflow_auth_state` no Supabase do painel - fonte
        compartilhada entre rodada local e o cron do GitHub Actions (que nao
        tem filesystem persistente entre execucoes). Sem isso, toda rodada
        do Actions cai pro login por senha - e desde que o MilhasFlow ligou
        protecao de captcha nesse endpoint (14/09/2026), login por senha sem
        captcha_token sempre falha. Falha em silencio (None): quem chama cai
        pro arquivo local."""
        if not self._tem_painel():
            return None
        try:
            linhas = supabase_rest.select(
                self.cfg.supabase_web_url, self.cfg.supabase_web_service_key,
                "milhasflow_auth_state", {"id": "eq." + MILHASFLOW_AUTH_ID, "select": "*"})
            return linhas[0] if linhas else None
        except Exception:
            return None

    def _tokens_salvos(self):
        remoto = self._tokens_remotos()
        if remoto:
            return remoto
        if not os.path.exists(self.cfg.caminho_tokens):
            return None
        try:
            with open(self.cfg.caminho_tokens, "r", encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, IOError):
            return None

    def _guardar_tokens(self, dados):
        conteudo = {
            "access_token": dados.get("access_token"),
            "refresh_token": dados.get("refresh_token"),
            "expira_em": int(time.time()) + int(dados.get("expires_in", 3600)),
        }
        # arquivo local sempre (rapido, funciona sem painel configurado)
        with open(self.cfg.caminho_tokens, "w", encoding="utf-8") as f:
            json.dump(conteudo, f)
        os.chmod(self.cfg.caminho_tokens, 0o600)  # so o dono le
        # + painel quando configurado - e ele quem sincroniza local <-> cron.
        # Falha aqui NAO pode derrubar a chamada (o access_token novo ja e
        # valido de qualquer jeito); so significa que a proxima rodada em
        # outro lugar pode nao ver o token mais recente.
        if self._tem_painel():
            # Perder esta escrita e catastrofico (o refresh_token velho ja
            # foi consumido, "already used" pra sempre) - por isso retry com
            # backoff aqui, nao so uma tentativa. Ver incidente de 15/09 e
            # 17/09/2026 na docstring de _tokens_remotos.
            ultimo_erro = None
            for tentativa_n in range(3):
                try:
                    supabase_rest.upsert(
                        self.cfg.supabase_web_url, self.cfg.supabase_web_service_key,
                        "milhasflow_auth_state", [{
                            "id": MILHASFLOW_AUTH_ID,
                            "access_token": conteudo["access_token"],
                            "refresh_token": conteudo["refresh_token"],
                            "expira_em": conteudo["expira_em"],
                        }], on_conflict="id")
                    ultimo_erro = None
                    break
                except Exception as erro:
                    ultimo_erro = erro
                    if tentativa_n < 2:
                        time.sleep(1.5 * (tentativa_n + 1))
            if ultimo_erro is not None:
                # nao pode derrubar a chamada (o access_token novo ja e
                # valido de qualquer jeito), mas precisa aparecer no log:
                # se isso falhar, o refresh_token novo nunca chega no
                # painel e a proxima rodada (maquina nova, sem este
                # processo em memoria) vai reusar o refresh_token velho -
                # que ja foi consumido agora e o Supabase rejeita como
                # "already used", derrubando a automacao inteira (foi
                # exatamente o que aconteceu em 15/09/2026).
                print("AVISO: nao consegui salvar o token renovado no "
                      "painel apos 3 tentativas (%s) - a proxima rodada "
                      "pode cair pro refresh_token antigo e falhar."
                      % ultimo_erro, file=sys.stderr)
        self._access_token = conteudo["access_token"]
        self._expira_em = conteudo["expira_em"]

    def _autenticar(self, grant, corpo):
        url = "%s/auth/v1/token?grant_type=%s" % (self.cfg.supabase_url, grant)
        resposta = self._requisitar(url, "POST", corpo, autenticado=False)
        if not resposta or not resposta.get("access_token"):
            raise ErroMilhasFlow("Login nao retornou token.")
        self._guardar_tokens(resposta)

    def _token(self, folga=60):
        """Devolve um access_token valido por mais `folga` segundos,
        renovando quando necessario.

        Com VOLLY_SEM_RENOVAR=1 (sessao do monitor Volly fora da fila
        milhasflow-auth, ver checar-volly-cloud.yml) nunca renova: so usa o
        token que a etapa anterior ja deixou valido no painel. Renovar fora
        da fila e justamente a corrida do refresh_token giratorio que
        derrubou tudo em 17/09/2026.
        """
        agora = int(time.time())

        if self._access_token and self._expira_em - folga > agora:
            return self._access_token

        salvos = self._tokens_salvos()
        if salvos and salvos.get("access_token") and salvos.get("expira_em", 0) - folga > agora:
            self._access_token = salvos["access_token"]
            self._expira_em = salvos["expira_em"]
            return self._access_token
        if os.environ.get("VOLLY_SEM_RENOVAR"):
            raise ErroMilhasFlow("token da Volly vencido e renovacao desligada nesta etapa "
                                 "(VOLLY_SEM_RENOVAR) - fica pra proxima sessao")
        if salvos:
            if salvos.get("refresh_token"):
                tentativa = salvos["refresh_token"]
                # refresh_token do Supabase e giratorio (uso unico): se
                # outra rodada (mover-crm, checar-latam, checar-gol, ...)
                # rodou entre a nossa leitura e agora, o nosso valor ja
                # morreu e vem "refresh_token_already_used". Antes de
                # desistir pro login por senha (bloqueado por captcha
                # desde 14/09/2026), rele o painel: se ja tem um valor
                # diferente do que acabamos de tentar, quem venceu a
                # corrida ja deixou um token novo la - tenta esse uma vez.
                #
                # 5 tentativas com espera crescente (nao mais 2 sem espera):
                # o vencedor da corrida ainda esta escrevendo o token novo
                # no painel quando o perdedor rele - sem pausa, a releitura
                # so pega o mesmo valor ja morto e desiste cedo demais (raiz
                # do incidente de 17/09/2026, alem da corrida em si).
                for indice in range(5):
                    try:
                        self._autenticar("refresh_token",
                                         {"refresh_token": tentativa})
                        return self._access_token
                    except ErroMilhasFlow:
                        if indice < 4:
                            time.sleep(2 * (indice + 1))
                        remoto = self._tokens_remotos()
                        novo = (remoto or {}).get("refresh_token")
                        if novo and novo != tentativa:
                            tentativa = novo
                            continue
                        if indice == 4:
                            break  # sem novidade: refresh morreu de verdade

        self._autenticar("password",
                         {"email": self.cfg.email, "password": self.cfg.senha})
        return self._access_token

    def garantir_token(self, folga_s):
        """Deixa no painel um access_token valido por pelo menos `folga_s`
        segundos (renova agora se faltar menos). Roda DENTRO da fila
        milhasflow-auth, antes de uma sessao longa que corre fora dela."""
        self._access_token = None
        self._expira_em = 0
        self._token(folga=folga_s)
        return self._expira_em

    # ------------------------------------------------------------------ Dados

    def _buscar_tabela(self, tabela, params):
        """Busca todas as linhas de uma tabela, paginando."""
        linhas = []
        offset = 0
        while True:
            consulta = dict(params)
            consulta["limit"] = PAGINA
            consulta["offset"] = offset
            url = "%s/rest/v1/%s?%s" % (
                self.cfg.supabase_url, tabela,
                urllib.parse.urlencode(consulta, safe="(),.*:"),
            )
            lote = self._requisitar(url) or []
            linhas.extend(lote)
            if len(lote) < PAGINA:
                return linhas
            offset += PAGINA

    def buscar_voos(self, so_com_emissao=True):
        """Tabela `reminders`: um registro por trecho de voo.

        `so_com_emissao=False` traz tambem trecho cadastrado na aba Voos sem
        emissao vinculada (11 dos 191 futuros em 26/09/2026) - a sincronizacao
        da nuvem quer TODO voo que esta na Volly, nao so os com venda.
        """
        direcoes = ",".join('"%s"' % d for d in DIRECOES_IGNORADAS)
        params = {
            "select": CAMPOS_VOO,
            "organization_id": "eq." + self.cfg.organization_id,
            "flight_direction": "not.in.(%s)" % direcoes,
        }
        if so_com_emissao:
            params["emission_id"] = "not.is.null"
        return self._buscar_tabela("reminders", params)

    def buscar_tags(self):
        """{emission_id: [nome da tag, ...]}.

        As tags carregam informacao de operacao que nao esta em nenhum campo:
        e por elas que a agencia marca 'Balcao' (venda feita para outra
        agencia). Essas continuam sendo checadas - a responsabilidade e
        compartilhada - mas o alerta precisa dizer que e balcao, porque quem
        avisa o passageiro e a outra ponta.
        """
        tags = {t["id"]: t["name"]
                for t in self._buscar_tabela("tags", {"select": "id,name"})}
        vinculos = self._buscar_tabela("emission_tags",
                                       {"select": "emission_id,tag_id"})
        por_emissao = {}
        for v in vinculos:
            nome = tags.get(v.get("tag_id"))
            if nome:
                por_emissao.setdefault(v["emission_id"], []).append(nome)
        return por_emissao

    def buscar_emissoes(self):
        """Tabela `emissions`: a venda, com cliente e passageiros."""
        return self._buscar_tabela("emissions", {
            "select": CAMPOS_EMISSAO,
            "organization_id": "eq." + self.cfg.organization_id,
        })

    def buscar_links_latam(self, emissao_ids):
        """emission_link/ticket_file_url das emissoes LATAM dadas - de onde
        checar_latam_cloud.py monta o deep link sem PDF/iCloud (ver
        extrair_pedido_latam). Em lotes de 100: PostgREST tem limite de
        tamanho pra clausula `in.(...)`.
        """
        emissao_ids = list(emissao_ids)
        linhas = []
        for i in range(0, len(emissao_ids), 100):
            lote = emissao_ids[i:i + 100]
            linhas += self._buscar_tabela("emissions", {
                "select": CAMPOS_LINK_LATAM,
                "id": "in.(%s)" % ",".join(lote),
            })
        return linhas

    def buscar_links_latam_por_localizador(self, localizadores):
        """Mesmo que buscar_links_latam, casando por `localizador` - trecho que
        chegou ao painel sem emissao_id (ingestao antiga) mas cuja venda existe."""
        localizadores = sorted(set(localizadores))
        linhas = []
        for i in range(0, len(localizadores), 100):
            linhas += self._buscar_tabela("emissions", {
                "select": CAMPOS_LINK_LATAM,
                "localizador": "in.(%s)" % ",".join(localizadores[i:i + 100]),
            })
        return linhas

    def buscar_bilhetes_anexados(self):
        """Voucher/bilhete em PDF anexado na venda (`emission_attachments`,
        file_type 'ticket'). Usado por vouchers.py pra tirar o nome do
        passageiro quando a venda veio sem nome (07/10/2026). A RLS da Volly
        ja filtra pela organizacao - a tabela nao tem organization_id."""
        return self._buscar_tabela("emission_attachments", {
            "select": "emission_id,file_name,file_url",
            "file_type": "eq.ticket",
        })

    def baixar_anexo(self, file_url, limite_bytes=8 * 1024 * 1024):
        """Bytes de um anexo da venda. O `file_url` gravado aponta pra
        /object/public/, mas o bucket `tickets` e privado ("Bucket not
        found" em 07/10/2026) - o mesmo arquivo sai pelo /object/authenticated/
        com o token do usuario."""
        url = file_url.replace("/object/public/", "/object/authenticated/", 1)
        req = urllib.request.Request(url, headers={
            "apikey": self.cfg.anon_key,
            "Authorization": "Bearer " + self._token(),
            "User-Agent": USER_AGENT_NAVEGADOR,
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                dados = resp.read(limite_bytes + 1)
        except urllib.error.HTTPError as e:
            raise ErroMilhasFlow("HTTP %s ao baixar anexo %s" % (e.code, url.split("?")[0]))
        except urllib.error.URLError as e:
            raise ErroMilhasFlow("Falha de conexao ao baixar anexo: %s" % e.reason)
        if len(dados) > limite_bytes:
            raise ErroMilhasFlow("anexo maior que %d bytes: %s" % (limite_bytes, url))
        return dados

    # --------------------------------------------------- Monitorar voo

    def buscar_snapshots_voo(self, numeros_voo):
        """Ultima leitura do "Monitorar voo" da Volly por (numero, data).

        `flight_status_snapshots` e um cache GLOBAL da Volly (sem
        organization_id, compartilhado entre todas as agencias): qualquer
        agencia que clicar no mesmo voo atualiza a linha pra todo mundo.
        `raw` e a resposta crua da AeroDataBox - mesmo formato que
        malha.ler_resposta ja le. Mesmo select em lotes de 150 que o proprio
        site usa (listSnapshots no bundle, 25/09/2026).
        """
        numeros = [n for n in dict.fromkeys(numeros_voo) if n]
        linhas = []
        for i in range(0, len(numeros), 150):
            lote = numeros[i:i + 150]
            linhas += self._buscar_tabela("flight_status_snapshots", {
                "select": "flight_number,flight_date,fetched_at,status,raw",
                "flight_number": "in.(%s)" % ",".join(lote),
            })
        return linhas

    def buscar_reminder(self, reminder_id):
        """Um trecho (`reminders`) pelo id, ou None se nao existir mais.

        So LEITURA: a reconferencia (reconferir_cloud.py) compara o que a
        Volly tem cadastrado com a companhia e PROPOE a mudanca - nunca
        escreve em `reminders` (decisao de 26/09/2026, a escrita e fase
        seguinte). `updated_at` vem junto pra conferir que ninguem mexeu.
        """
        linhas = self._buscar_tabela("reminders", {
            "select": "id,locator,flight_number,airline,departure_airport,"
                      "arrival_airport,departure_datetime,arrival_datetime,"
                      "emission_id,updated_at,checkin_notification,"
                      "reminder_date,status,notify_whatsapp,flight_direction,"
                      "miles_transaction_id,passenger_name",
            "organization_id": "eq." + self.cfg.organization_id,
            "id": "eq." + reminder_id,
        })
        return linhas[0] if linhas else None

    def atualizar_reminder(self, reminder_id, campos):
        """PATCH num trecho (`reminders`) - a UNICA escrita do sistema de
        voos na Volly (aplicar_volly_cloud.py, depois de clique humano em
        "Aplicar na Volly" e com a chave APLICAR_VOLLY=real). Liberada pelo
        o proprietário em 27/09/2026.

        Devolve a linha gravada. Filtra por organizacao alem do id: nunca
        toca trecho de outra agencia mesmo com id errado.
        """
        url = "%s/rest/v1/reminders?id=eq.%s&organization_id=eq.%s" % (
            self.cfg.supabase_url, reminder_id, self.cfg.organization_id)
        linhas = self._requisitar(url, "PATCH", campos,
                                  cabecalhos={"Prefer": "return=representation"})
        if not linhas:
            raise ErroMilhasFlow("PATCH em reminders nao devolveu linha (id %s)" % reminder_id)
        return linhas[0]

    def consultar_status_voo(self, reminder_id, forcar=False):
        """Aperta o botao "Monitorar voo" da Volly: edge function
        `flight-status` com o id do trecho (reminders.id = voos.id do painel).

        Devolve (resposta, erro). A Volly consulta a AeroDataBox na cota
        DELA e grava o resultado em flight_status_snapshots/_changes;
        `forcar` ignora o cache deles. 404 "Voo nao encontrado" e normal pra
        voo noturno: a Volly monta a data em UTC (bug deles, confirmado com
        G3 2029 21h40 local em 25/09/2026) - quem cobre esse voo e a malha.
        """
        url = "%s/functions/v1/flight-status" % self.cfg.supabase_url
        try:
            resposta = self._requisitar(
                url, "POST", {"reminderId": reminder_id, "force": bool(forcar)})
        except ErroMilhasFlow as e:
            return None, str(e).split("\n")[-1][:200]
        if not resposta or resposta.get("error"):
            return None, (resposta or {}).get("error") or "resposta vazia"
        return resposta, None

    # ------------------------------------------------------------- CRM

    def buscar_colunas_crm(self):
        """Tabela `crm_columns` do funil Pos-Venda: column_key, titulo e a
        configuracao de mensagem/prazo de cada coluna."""
        return self._buscar_tabela("crm_columns", {
            "select": CAMPOS_COLUNA_CRM,
            "organization_id": "eq." + self.cfg.organization_id,
            "funnel_id": "eq." + POS_VENDA_FUNNEL_ID,
        })

    def buscar_cotacoes_crm(self):
        """Cards do funil Pos-Venda (`crm_quote_placements`) com a cotacao
        embutida - mesmo select que o proprio site usa pra carregar o board.
        """
        return self._buscar_tabela("crm_quote_placements", {
            "select": CAMPOS_PLACEMENT_CRM,
            "organization_id": "eq." + self.cfg.organization_id,
            "funnel_id": "eq." + POS_VENDA_FUNNEL_ID,
            "deleted_at": "is.null",
            "quote.deleted_at": "is.null",
        })

    def buscar_clientes_crm(self, client_ids):
        """{client_id: {id,name,phone}} dos clientes dados, num lote so (em
        lotes de 100 - mesmo padrao de buscar_links_latam) em vez de uma
        consulta por cliente.

        Nome do campo de telefone (`phone`) e a UNICA peca deste modulo
        ainda nao confirmada contra a API real - ver Fase 3 do plano. Se o
        campo tiver outro nome, o telefone sai vazio (nao quebra a rodada)
        e precisa de ajuste.
        """
        client_ids = [c for c in dict.fromkeys(client_ids) if c]
        linhas = []
        for i in range(0, len(client_ids), 100):
            lote = client_ids[i:i + 100]
            linhas += self._buscar_tabela("clients", {
                "select": "id,name,phone",
                "id": "in.(%s)" % ",".join(lote),
            })
        return {l["id"]: l for l in linhas}

    def mover_cotacao_crm(self, placement_id, quote_id, column_key_novo, position_novo,
                          client_id, telefone, ddi, mensagem, agendar_para, tocado_em):
        """Replica os 4 passos que o proprio site faz ao arrastar um card
        (capturado via DevTools em 24/08/2026 - ver a spec, secao
        Arquitetura), mas na ordem que deixa uma falha no meio do caminho
        segura: cria o agendamento da mensagem NOVA primeiro. Se essa
        chamada falhar, nada mais mudou ainda - o card nem foi movido, sem
        risco de ficar "mudou de coluna mas o cliente nunca foi avisado"
        (a ordem original, mensagem por ultimo, tinha exatamente esse
        risco). So depois disso move o card de verdade, e por fim limpa
        qualquer agendamento pendente antigo (excluindo o que acabou de
        criar).

        `mensagem=None` pula a criacao de agendamento inteira - caso de
        coluna terminal sem `whatsapp_message` configurado (ex: Concluido),
        onde de fato nao ha o que mandar; so move o card e limpa o que
        estava pendente.
        """
        base = self.cfg.supabase_url

        # 1. cria o agendamento que vai disparar a mensagem NOVA - primeiro
        # de proposito (ver docstring). return=representation pra saber o
        # id e nao apaga-lo no passo 3.
        novo_id = None
        if mensagem:
            url_agendar = "%s/rest/v1/crm_quote_scheduled_messages" % base
            criado = self._requisitar(url_agendar, "POST", {
                "organization_id": self.cfg.organization_id,
                "auto_key": None,
                "client_id": client_id,
                "client_phone": telefone,
                "phone_country_code": ddi,
                "column_key": column_key_novo,
                "context_type": "quote",
                "is_auto": True,
                "message": mensagem,
                "quote_id": quote_id,
                "scheduled_at": agendar_para,
            }, cabecalhos={"Prefer": "return=representation"})
            novo_id = (criado or [{}])[0].get("id")

        # 2. move o placement
        url_placement = "%s/rest/v1/crm_quote_placements?id=eq.%s" % (base, placement_id)
        self._requisitar(url_placement, "PATCH",
                         {"column_key": column_key_novo, "position": position_novo},
                         cabecalhos={"Prefer": "return=minimal"})

        # 3. toca a cotacao - o site so atualiza esse campo, nao o `status`
        url_quote = "%s/rest/v1/crm_quotes?id=eq.%s" % (base, quote_id)
        self._requisitar(url_quote, "PATCH", {"last_activity_at": tocado_em},
                         cabecalhos={"Prefer": "return=minimal"})

        # 4. apaga agendamento pendente ANTIGO desta cotacao, sem tocar no
        # que acabou de ser criado no passo 1
        filtro = {
            "quote_id": "eq." + quote_id,
            "status": "eq.pending",
            "is_auto": "eq.true",
        }
        if novo_id:
            filtro["id"] = "neq." + novo_id
        url_delete = "%s/rest/v1/crm_quote_scheduled_messages?%s" % (
            base, urllib.parse.urlencode(filtro))
        self._requisitar(url_delete, "DELETE", cabecalhos={"Prefer": "return=minimal"})
