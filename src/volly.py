"""Cliente de LEITURA da Volly (ex-MilhasFlow) direto no Supabase/PostgREST.

Substitui o MCP pago da Volly (`volly.com.br/mcp`, 1 credito por chamada) pelo
mesmo caminho que o robo de CRM (`milhasflow.py`) ja usa: autentica como o
proprio usuario da agencia (email/senha -> token Supabase) e consulta as
tabelas que a interface consulta. Custo por chamada: zero.

Aqui e SO leitura. As somas (lucro do mes, LTV, margem, conformidade fiscal)
sao feitas em `gestao.py`, em Python - a Volly nao calcula nada pra gente.

Tabelas confirmadas por sondagem em 2026-09-10 (scratchpad/probe.py). O que
NAO foi encontrado nesse Supabase e fica de fora ate um print da aba Network:
  - conversas/mensagens do VollyChat (Flowchat roda em outro backend)
  - extrato de pontos por conta (provavel: derivado de emissoes+transferencias)
  - tabela de perfil fiscal (o nome do perfil ja vem em nfse_emissoes)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config as _config_padrao
from milhasflow import MilhasFlow, ErroMilhasFlow  # noqa: F401  (reexport do erro)

# Funis conhecidos (ids capturados no site). O de Pos-Venda ja vivia em
# milhasflow.POS_VENDA_FUNNEL_ID; os outros dois vieram de crm_funnels_list.
FUNIL_POS_VENDA = "3206aaa9-8cf1-4b31-8aca-f1737a8c9ad8"


class Volly(object):
    def __init__(self, config=None, mf=None):
        self.cfg = config or _config_padrao
        self.org = self.cfg.organization_id
        # reaproveita HTTP + auth + cache de token do robo que ja roda
        # (mf: quem ja tem um MilhasFlow logado passa o dele, sem 2o login)
        self._mf = mf or MilhasFlow(self.cfg)

    # ------------------------------------------------------------ infra

    def _tab(self, tabela, select="*", filtros=None, ordem=None, com_org=True):
        params = {"select": select}
        if com_org:
            params["organization_id"] = "eq." + self.org
        if filtros:
            params.update(filtros)
        if ordem:
            params["order"] = ordem
        return self._mf._buscar_tabela(tabela, params)

    @staticmethod
    def _entre(campo, inicio, fim):
        """Filtro de intervalo [inicio, fim] num campo de data/datetime.

        PostgREST nao aceita a mesma chave duas vezes num dict, entao vai
        como `and=(campo.gte.X,campo.lte.Y)`.
        """
        partes = []
        if inicio:
            partes.append("%s.gte.%s" % (campo, inicio))
        if fim:
            partes.append("%s.lte.%s" % (campo, fim))
        if not partes:
            return {}
        if len(partes) == 1:
            campo, _, resto = partes[0].partition(".")  # 'x.gte.2026-01-01'
            return {campo: resto}                       # -> {'x': 'gte.2026-01-01'}
        return {"and": "(%s)" % ",".join(partes)}

    def saude(self, tabelas=None):
        """Confere que cada tabela ainda responde. Vira o teste de schema:
        se a Volly renomear algo, isto acusa antes do relatorio quebrar.
        """
        alvo = tabelas or [
            "emissions", "clients", "financial_transactions",
            "financial_accounts", "transaction_categories", "suppliers",
            "subscriptions", "miles_accounts", "miles_transfers",
            "miles_recurrences", "crm_funnels", "crm_columns", "crm_quotes",
            "crm_quote_placements", "crm_followups", "nfse_emissoes",
            "profiles", "organization_members", "team_goals", "team_tasks",
            "team_boards", "team_board_columns", "whatsapp_connections",
        ]
        resultado = {}
        for t in alvo:
            try:
                # select=id, nao *: `clients` devolve HTTP 500 com select=*
                # (coluna/relacao gerada quebrada no lado da Volly).
                self._mf._buscar_tabela(t, {"select": "id", "limit": 1})
                resultado[t] = "ok"
            except ErroMilhasFlow as e:
                resultado[t] = str(e).split("\n")[0]
        return resultado

    # ------------------------------------------------------------ emissoes

    CAMPOS_EMISSAO = (
        "id,emission_date,emission_type,sale_value,total_cost,profit,"
        "profit_margin,commission,emissor_commission_value,emissor_id,"
        "client_id,crm_quote_id,localizador,payment_status,payment_date,"
        "supplier_id,supplier_payment_status,is_miles_sale,is_miles_purchase,"
        "miles_account_id,miles_quantity,miles_cost,extra_profit,"
        "financial_verified,refund_status,created_at"
    )

    def emissoes(self, inicio=None, fim=None):
        """`emissions` no periodo (por emission_date). Sem periodo = tudo."""
        return self._tab("emissions", self.CAMPOS_EMISSAO,
                         self._entre("emission_date", inicio, fim),
                         ordem="emission_date.desc")

    # ------------------------------------------------------------ clientes

    CAMPOS_CLIENTE = (
        "id,name,first_name,last_name,person_type,cpf,cnpj,email,phone,"
        "phone_country_code,birth_date,gender,lead_source,client_tags,"
        "customer_since,created_at,account_manager_id,parent_company_id,"
        "membership_plan_name,membership_ends_on,monthly_spending,"
        "birthday_reminder_enabled,notes,travel_preferences"
    )

    def clientes(self):
        return self._tab("clients", self.CAMPOS_CLIENTE, ordem="created_at.desc")

    # ------------------------------------------------------------ financeiro

    CAMPOS_TRANSACAO = (
        "id,type,amount,description,is_paid,payment_date,competence_date,"
        "transaction_date,invoice_due_date,category_id,account_id,"
        "destination_account_id,supplier_id,client_id,emission_id,"
        "points_purchase_id,recurrence_type,recurrence_parent_id,reconciled,"
        "service_key,crm_correlation_key,current_installment,created_at"
    )

    def transacoes(self, inicio=None, fim=None, campo="competence_date"):
        """`financial_transactions`. `campo` = a data que define o periodo
        (competence_date pro regime competencia, payment_date pro caixa)."""
        return self._tab("financial_transactions", self.CAMPOS_TRANSACAO,
                         self._entre(campo, inicio, fim),
                         ordem=campo + ".desc")

    def transacoes_em_aberto(self, tipo=None):
        """Nao pagas (a pagar / a receber). tipo: 'income'|'expense'|None.
        O nome exato do valor em `type` sai da 1a rodada - ver gestao.py."""
        filtros = {"is_paid": "eq.false"}
        if tipo:
            filtros["type"] = "eq." + tipo
        return self._tab("financial_transactions", self.CAMPOS_TRANSACAO,
                         filtros, ordem="invoice_due_date.asc")

    def contas(self):
        return self._tab("financial_accounts",
                         "id,name,type,current_balance,initial_balance,"
                         "is_active,billing_closing_day,billing_due_day")

    def categorias(self):
        """Categorias da org + as de sistema (globais, sem organization_id -
        ex: a receita de emissao `20000000-0000-0000-0000-000000000001`)."""
        campos = ("id,name,type,parent_id,is_system,is_active,"
                  "overrides_category_id")
        proprias = self._tab("transaction_categories", campos)
        sistema = self._mf._buscar_tabela("transaction_categories", {
            "select": campos, "is_system": "eq.true",
        })
        vistos = {c["id"] for c in proprias}
        return proprias + [c for c in sistema if c["id"] not in vistos]

    def fornecedores(self):
        return self._tab("suppliers",
                         "id,name,razao_social,cpf_cnpj,phone,email,status,"
                         "supplier_tags")

    def assinaturas(self):
        return self._tab("subscriptions",
                         "id,status,cycle,total_value,base_value,next_due_date,"
                         "started_at,trial_ends_at,flowchat_activated,"
                         "flowchat_agents,seat_count")

    def faturas_cartao(self):
        return self._tab("credit_card_invoices", "*")

    # ------------------------------------------------------------ milhas

    def milhas_contas(self):
        return self._tab("miles_accounts",
                         "id,name,program,account_type,status,balance,cpm,"
                         "cpf_limit,cpf_used,total_invested,account_profit,"
                         "suggested_sale_price,priority,holder_cpf,"
                         "holder_birthday,club_active,club_monthly_cost,"
                         "club_points_monthly,club_due_day,"
                         "club_annual_renewal_date,club_annual_alert_days,"
                         "club_renewal_pending,club_reminder_enabled,"
                         "club_member_since,club_months_active,wallet")

    def milhas_clubes(self):
        """Contas com clube ativo ou que ja tiveram (club_member_since), sem CPF."""
        return self._tab("miles_accounts",
                         "id,name,program,club_active,club_monthly_cost,"
                         "club_points_monthly,club_due_day,club_member_since,"
                         "club_months_active",
                         {"or": "(club_active.eq.true,club_member_since.not.is.null)"})

    def milhas_transferencias(self, inicio=None, fim=None):
        return self._tab("miles_transfers",
                         "id,transfer_date,source_account_id,"
                         "destination_account_id,source_total_points,"
                         "source_points_own,source_points_purchased,"
                         "source_purchase_amount,destination_miles,"
                         "bonus_percentage,parity_ratio,source_cpm,"
                         "destination_cpm,express_points,is_draft,description",
                         self._entre("transfer_date", inicio, fim),
                         ordem="transfer_date.desc")

    def emissoes_passageiros(self, inicio=None):
        """Emissoes com conta de milhas e passageiros (pra contar CPF por conta)."""
        return self._tab("emissions",
                         "id,emission_date,miles_account_id,passengers_data,refund_status",
                         dict(self._entre("emission_date", inicio, None),
                              miles_account_id="not.is.null"))

    def milhas_recorrencias(self, so_ativas=True):
        filtros = {"is_active": "eq.true"} if so_ativas else None
        return self._tab("miles_recurrences",
                         "id,account_id,type,frequency,miles_quantity,"
                         "amount_paid,cpm,due_day,start_month,end_date,"
                         "is_active,require_confirmation,description", filtros)

    # ------------------------------------------------------------ CRM

    def crm_funis(self):
        return self._tab("crm_funnels",
                         "id,name,is_default,visibility,position,"
                         "show_followup_suggestions")

    def crm_colunas(self, funil_id=None):
        filtros = {"funnel_id": "eq." + funil_id} if funil_id else None
        return self._tab("crm_columns",
                         "id,funnel_id,column_key,title,stage_type,position,"
                         "visible,followup_enabled,followup_days,followup_time,"
                         "whatsapp_message,max_days_in_stage,is_lead_qualifier",
                         filtros, ordem="position.asc")

    def crm_cotacoes(self, funil_id=None):
        filtros = {"deleted_at": "is.null"}
        if funil_id:
            filtros["funnel_id"] = "eq." + funil_id
        return self._tab("crm_quotes",
                         "id,funnel_id,title,status,client_id,client_name,"
                         "responsible_id,responsible_name,total_value,"
                         "total_cost,profit,tags,sale_date,last_activity_at,"
                         "created_at,emission_id,flights", filtros,
                         ordem="last_activity_at.desc")

    def crm_placements(self, funil_id=None):
        filtros = {"deleted_at": "is.null"}
        if funil_id:
            filtros["funnel_id"] = "eq." + funil_id
        return self._tab("crm_quote_placements",
                         "id,funnel_id,quote_id,column_key,position,is_primary,"
                         "stage_entered_at,created_at", filtros)

    def crm_followups(self, status=None):
        filtros = {"status": "eq." + status} if status else None
        return self._tab("crm_followups",
                         "id,quote_id,column_key,followup_date,status,"
                         "created_at", filtros, ordem="followup_date.asc")

    # ------------------------------------------------------------ NFS-e

    def nfse(self, inicio=None, fim=None):
        return self._tab("nfse_emissoes",
                         "id,emission_id,status,numero_nfse,numero_rps,"
                         "authorized_at,cancelled_at,cancelamento_status,"
                         "data_competencia,valor_servico,valor_iss,"
                         "aliquota_iss,tomador_nome,tomador_documento,"
                         "fiscal_profile_nome,erro_mensagem,url_pdf,url_xml,"
                         "created_at",
                         self._entre("created_at", inicio, fim),
                         ordem="created_at.desc")

    # ------------------------------------------------------------ equipe

    def equipe_perfis(self):
        return self._tab("profiles",
                         "id,full_name,email,phone,is_active,created_at")

    def equipe_membros(self):
        return self._tab("organization_members",
                         "id,user_id,role,is_owner,status,"
                         "permission_profile_id,created_at")

    def equipe_metas(self, so_ativas=True):
        return self._tab("team_goals", "*")

    def equipe_tarefas(self, status=None):
        filtros = {"status": "eq." + status} if status else None
        return self._tab("team_tasks",
                         "id,title,description,status,priority,assigned_to,"
                         "created_by,board_id,board_column_id,due_date,"
                         "due_time,source_quote_id,recurrence_type,created_at",
                         filtros, ordem="due_date.asc")

    def equipe_boards(self):
        return self._tab("team_boards",
                         "id,name,board_type,is_default,visibility,position")

    def equipe_board_colunas(self, board_id=None):
        filtros = {"board_id": "eq." + board_id} if board_id else None
        return self._tab("team_board_columns",
                         "id,board_id,name,position,color", filtros,
                         ordem="position.asc")

    # ------------------------------------------------------------ chat (parcial)

    def chat_conexoes(self):
        """So as linhas de WhatsApp. O resto do VollyChat (conversas,
        mensagens, protocolos) nao esta neste Supabase - ver docstring do
        modulo."""
        return self._tab("whatsapp_connections",
                         "id,connection_id,connection_name,phone_number,"
                         "status,created_at,updated_at")


if __name__ == "__main__":
    # Fumaça: lista quantas linhas cada dominio devolve hoje.
    v = Volly()
    print("saude:")
    for tabela, estado in v.saude().items():
        print("  %-28s %s" % (tabela, estado))
