"""Cliente de LEITURA do VollyChat - backend Supabase SEPARADO da Volly
principal (descoberto 2026-09-12: bundle de `volly.com.br` referencia
`chat.volly.com.br`, cujo app carrega `SEU_PROJETO_CHAT.supabase.co`,
projeto diferente do `SEU_PROJETO_MILHASFLOW` que `milhasflow.py`/`volly.py`
usam).

Auth diferente de tudo que o projeto ja tinha: essa conta e federada por
SSO/OTP (`amr: [{"method":"otp"}]` no JWT capturado via DevTools) - login
por email/senha (grant_type=password) NAO funciona aqui, confirmado na
pratica. O unico jeito e o `refresh_token` que o navegador guarda no
localStorage (`sb-SEU_PROJETO_CHAT-auth-token`), extraido uma vez a
mao. Ele GIRA a cada uso (Supabase invalida o antigo e devolve um novo) -
por isso `.tokens_chat.json` existe: guarda o refresh_token mais recente
pra sobreviver entre execucoes, exatamente como `.tokens.json` faz pro
MilhasFlow, so que aqui NAO HA fallback de senha se o refresh morrer (ver
ErroTokenChatExpirado).

Tabelas confirmadas (probe autenticado 2026-09-12): conversations,
messages, wa_connections, protocols, quick_replies, organizations,
memberships, conversation_tags, tags, import_jobs, conversation_pins,
conversation_events, conversation_reads, contacts. NAO encontradas/sem
acesso: message_reactions e org_ai_identities com select=* (500/404) -
message_reactions da pra pegar embutido numa query de conversations, como
o proprio site faz.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import supabase_rest
from milhasflow import USER_AGENT_NAVEGADOR

PAGINA = 1000
CHAT_AUTH_ID = "lfviagens"  # linha fixa em chat_auth_state (ver migration)


class ErroVollyChat(Exception):
    pass


class ErroTokenChatExpirado(ErroVollyChat):
    """O refresh_token guardado nao serve mais. Nao ha grant de senha pra
    cair de volta (SSO/OTP) - precisa recapturar do localStorage do
    navegador (ver docstring do modulo) e atualizar CHAT_REFRESH_TOKEN no
    .env (ou .tokens_chat.json direto)."""


class VollyChat(object):
    def __init__(self, config):
        self.cfg = config
        self._access_token = None
        self._expira_em = 0

    # ------------------------------------------------------------------ HTTP

    def _requisitar(self, url, metodo="GET", corpo=None, cabecalhos=None, autenticado=True):
        headers = {
            "apikey": self.cfg.chat_anon_key,
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

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                bruto = resp.read().decode("utf-8")
                return json.loads(bruto) if bruto else None
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode("utf-8", "replace")[:400]
            raise ErroVollyChat("HTTP %s em %s\n%s" % (e.code, url.split("?")[0], detalhe))
        except urllib.error.URLError as e:
            raise ErroVollyChat("Falha de conexao: %s" % e.reason)

    # ------------------------------------------------------------------ Auth

    def _tem_painel(self):
        return bool(self.cfg.supabase_web_url and self.cfg.supabase_web_service_key)

    def _tokens_remotos(self):
        """`chat_auth_state` no Supabase do painel - fonte compartilhada
        entre rodada local e o cron do GitHub Actions (que nao tem
        filesystem persistente entre execucoes). Falha em silencio (None):
        quem chama cai pro arquivo local."""
        if not self._tem_painel():
            return None
        try:
            linhas = supabase_rest.select(
                self.cfg.supabase_web_url, self.cfg.supabase_web_service_key,
                "chat_auth_state", {"id": "eq." + CHAT_AUTH_ID, "select": "*"})
            return linhas[0] if linhas else None
        except Exception:
            return None

    def _tokens_salvos(self):
        remoto = self._tokens_remotos()
        if remoto:
            return remoto
        if not os.path.exists(self.cfg.caminho_tokens_chat):
            return None
        try:
            with open(self.cfg.caminho_tokens_chat, "r", encoding="utf-8") as f:
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
        with open(self.cfg.caminho_tokens_chat, "w", encoding="utf-8") as f:
            json.dump(conteudo, f)
        os.chmod(self.cfg.caminho_tokens_chat, 0o600)
        # + painel quando configurado - e ele quem sincroniza local <-> cron.
        # Falha aqui NAO pode derrubar a chamada (o access_token novo ja e
        # valido de qualquer jeito); so significa que a proxima rodada em
        # outro lugar pode nao ver o token mais recente.
        if self._tem_painel():
            try:
                supabase_rest.upsert(
                    self.cfg.supabase_web_url, self.cfg.supabase_web_service_key,
                    "chat_auth_state", [{
                        "id": CHAT_AUTH_ID,
                        "access_token": conteudo["access_token"],
                        "refresh_token": conteudo["refresh_token"],
                        "expira_em": conteudo["expira_em"],
                    }], on_conflict="id")
            except Exception:
                pass
        self._access_token = conteudo["access_token"]
        self._expira_em = conteudo["expira_em"]

    def _refresh_token_atual(self):
        """O mais recente conhecido: .tokens_chat.json se existir, senao a
        semente do .env (CHAT_REFRESH_TOKEN)."""
        salvos = self._tokens_salvos()
        if salvos and salvos.get("refresh_token"):
            return salvos["refresh_token"]
        return self.cfg.chat_refresh_token

    def _token(self):
        agora = int(time.time())
        if self._access_token and self._expira_em - 60 > agora:
            return self._access_token

        salvos = self._tokens_salvos()
        if salvos and salvos.get("access_token") and salvos.get("expira_em", 0) - 60 > agora:
            self._access_token = salvos["access_token"]
            self._expira_em = salvos["expira_em"]
            return self._access_token

        refresh = self._refresh_token_atual()
        if not refresh:
            raise ErroTokenChatExpirado(
                "CHAT_REFRESH_TOKEN nao configurado e nenhum .tokens_chat.json salvo.")

        url = self.cfg.chat_url + "/auth/v1/token?grant_type=refresh_token"
        try:
            resposta = self._requisitar(url, "POST", {"refresh_token": refresh},
                                        autenticado=False)
        except ErroVollyChat as e:
            raise ErroTokenChatExpirado(
                "Refresh falhou (%s). O token girou em outro lugar (navegador "
                "aberto?) ou expirou de vez - recaptura do localStorage "
                "necessaria (ver docstring de volly_chat.py)." % e)

        if not resposta or not resposta.get("access_token"):
            raise ErroTokenChatExpirado("Refresh nao devolveu token novo.")
        self._guardar_tokens(resposta)
        return self._access_token

    # ------------------------------------------------------------- Dados

    def _tab(self, tabela, select="*", filtros=None, ordem=None, com_org=True):
        params = {"select": select}
        if com_org:
            params["organization_id"] = "eq." + self.cfg.chat_organization_id
        if filtros:
            params.update(filtros)
        if ordem:
            params["order"] = ordem
        return self._buscar_tabela(tabela, params)

    def _buscar_tabela(self, tabela, params):
        linhas = []
        offset = 0
        while True:
            consulta = dict(params)
            consulta["limit"] = PAGINA
            consulta["offset"] = offset
            url = "%s/rest/v1/%s?%s" % (
                self.cfg.chat_url, tabela,
                urllib.parse.urlencode(consulta, safe="(),.*:!"),
            )
            lote = self._requisitar(url) or []
            linhas.extend(lote)
            if len(lote) < PAGINA:
                return linhas
            offset += PAGINA

    @staticmethod
    def _entre(campo, inicio, fim):
        partes = []
        if inicio:
            partes.append("%s.gte.%s" % (campo, inicio))
        if fim:
            partes.append("%s.lte.%s" % (campo, fim))
        if not partes:
            return {}
        if len(partes) == 1:
            campo_, _, resto = partes[0].partition(".")
            return {campo_: resto}
        return {"and": "(%s)" % ",".join(partes)}

    # Tabelas confirmadas SEM coluna organization_id propria (o filtro tem
    # que vir de outro lugar - normalmente join com conversation_id).
    SEM_ORG = ("organizations", "conversation_pins", "conversation_reads")

    def saude(self):
        alvo = ["conversations", "wa_connections", "protocols",
               "quick_replies", "organizations", "memberships",
               "conversation_tags", "tags", "import_jobs", "conversation_pins",
               "conversation_events", "conversation_reads", "contacts"]
        resultado = {}
        for t in alvo:
            # select=* (nao "id"): conversation_tags/conversation_pins/
            # conversation_reads sao tabelas de join, sem coluna id propria.
            params = {"select": "*", "limit": 1}
            if t not in self.SEM_ORG:
                params["organization_id"] = "eq." + self.cfg.chat_organization_id
            try:
                self._buscar_tabela(t, params)
                resultado[t] = "ok"
            except ErroVollyChat as e:
                resultado[t] = str(e).split("\n")[0]
        # messages nao tem organization_id nem filtro barato sem
        # conversation_id (ver mensagens_das_conversas) - aqui so confere
        # que a tabela responde, num unico id conhecido de antemao seria
        # ideal, mas sem isso um limit=1 sem filtro nenhum e o teste mais
        # barato possivel.
        try:
            self._requisitar("%s/rest/v1/messages?select=id&limit=1" % self.cfg.chat_url)
            resultado["messages"] = "ok"
        except ErroVollyChat as e:
            resultado["messages"] = str(e).split("\n")[0]
        return resultado

    # -------- conversas: mesmo select que o proprio VollyChat usa pra
    # carregar a lista (capturado via DevTools 2026-09-12) - so a ULTIMA
    # mensagem embutida, o suficiente pra saber quem falou por ultimo.
    CAMPOS_CONVERSA = (
        "id,status,wa_connection_id,assigned_to,responder_ids,claimed_at,"
        "ai_handoff_at,read_at,last_message_at,last_inbound_at,archived_at,"
        "created_at,"
        "contacts(id,name,custom_name,phone,display_phone,is_group),"
        "conversation_tags(tags(id,name,color)),"
        "messages(body,media_type,direction,sender_name,created_at)"
    )

    def conversas(self, so_abertas=True, wa_connection_id=None, desde=None):
        filtros = {"messages.order": "created_at.desc", "messages.limit": "1"}
        if so_abertas:
            filtros["archived_at"] = "is.null"
        if wa_connection_id:
            filtros["wa_connection_id"] = "eq." + wa_connection_id
        if desde:
            filtros["last_message_at"] = "gte." + desde
        return self._tab("conversations", self.CAMPOS_CONVERSA, filtros,
                         ordem="last_message_at.desc.nullslast")

    # -------- mensagens: `messages` e uma tabela COMPARTILHADA entre todos
    # os clientes da Volly (produto white-label) e nao tem organization_id
    # proprio - so `conversation_id`. Um filtro so por data escaneia a base
    # inteira e estoura timeout (confirmado na pratica 2026-09-12). O
    # caminho certo, igual o proprio site faz, e sempre filtrar por
    # conversation_id - por isso esta funcao pede a lista de conversas
    # primeiro (organization_id ali SIM existe e filtra bem) e so depois
    # busca as mensagens delas, em lotes.
    CAMPOS_MENSAGEM = (
        "id,conversation_id,direction,body,media_type,sender_name,"
        "author_user_id,created_at,is_internal_note,status,deleted_at"
    )

    def mensagens_das_conversas(self, conversation_ids, desde=None, ate=None):
        ids = list(dict.fromkeys(conversation_ids))
        linhas = []
        for i in range(0, len(ids), 50):
            lote = ids[i:i + 50]
            filtros = {"conversation_id": "in.(%s)" % ",".join(lote)}
            filtros.update(self._entre("created_at", desde, ate))
            linhas += self._buscar_tabela("messages", {
                "select": self.CAMPOS_MENSAGEM, "order": "created_at.asc",
                **filtros,
            })
        return linhas

    def mensagens_recentes(self, dias=7):
        """Conversas com atividade nos ultimos `dias` + as mensagens delas
        no mesmo periodo. E o caminho pratico pra tempo de resposta/volume
        sem tocar a tabela messages sem filtro de conversa."""
        import datetime as _dt
        desde = (_dt.date.today() - _dt.timedelta(days=dias)).isoformat()
        conversas = self.conversas(so_abertas=False, desde=desde)
        ids = [c["id"] for c in conversas]
        mensagens = self.mensagens_das_conversas(ids, desde=desde) if ids else []
        return conversas, mensagens

    def protocolos(self, inicio=None, fim=None):
        return self._tab("protocols",
                         "id,conversation_id,number,status,stage,subject,"
                         "opened_at,opened_by,closed_at,closed_by,"
                         "protocol_type_id",
                         self._entre("opened_at", inicio, fim),
                         ordem="opened_at.desc")

    def tags(self):
        return self._tab("tags", "id,name,color,position,show_in_board")

    def memberships(self):
        """Agentes/membros da organizacao no chat (nome pra exibir, nao
        confundir com organization_members da Volly principal - user_id
        aqui e o auth.uid() deste Supabase, outro id)."""
        return self._tab("memberships", "*")

    def conexoes(self):
        return self._tab("wa_connections",
                         "id,channel_type,evolution_instance,groups_only,"
                         "full_history_synced,business_hours_days,"
                         "business_hours_start,business_hours_end,"
                         "business_hours_tz,created_at")

    def organizacao(self):
        """`organizations` nao tem coluna organization_id - a linha em si
        E a organizacao, filtra por `id`."""
        linhas = self._tab("organizations",
                           "id,name,slug,auth_strategy,allow_password_login,"
                           "auto_assign,auto_assign_mode,read_mode,"
                           "protocol_counter,csat_message",
                           {"id": "eq." + self.cfg.chat_organization_id},
                           com_org=False)
        return linhas[0] if linhas else None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import config
    vc = VollyChat(config)
    print("saude:")
    for t, e in vc.saude().items():
        print("  %-22s %s" % (t, e))
