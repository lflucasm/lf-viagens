"""Leitura da configuracao a partir do arquivo .env na raiz do projeto."""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_ENV = os.path.join(RAIZ, ".env")
CAMINHO_IGNORADOS = os.path.join(RAIZ, "ignorados.txt")

OBRIGATORIOS = ("MILHASFLOW_EMAIL", "MILHASFLOW_SENHA", "MILHASFLOW_ANON_KEY")

PADROES = {
    "SUPABASE_URL": "https://SEU_PROJETO_MILHASFLOW.supabase.co",
    "ORGANIZATION_ID": "00000000-0000-0000-0000-000000000000",
    # VollyChat: backend Supabase SEPARADO da Volly principal (descoberto
    # 2026-09-12 - ver src/volly_chat.py). CHAT_ANON_KEY e CHAT_ORGANIZATION_ID
    # nao sao segredo (a anon key e publica no bundle JS, o org id aparece em
    # toda URL da rede) - ficam aqui so pra nao depender do .env pra isso.
    # CHAT_REFRESH_TOKEN esse sim e do .env (gira sozinho depois).
    "CHAT_URL": "https://SEU_PROJETO_CHAT.supabase.co",
    "CHAT_ANON_KEY": "COLE_A_ANON_KEY_AQUI",
    "CHAT_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000000",
    "PASTA_DADOS": "dados",
    # Malha (AeroDataBox). O default e o canal API.market, que e o do OpenAPI
    # oficial; quem assina pelo RapidAPI troca as duas linhas no .env.
    "MALHA_API_URL": "https://prod.api.market/api/v1/aedbx/aerodatabox",
    "MALHA_API_HEADER": "x-api-market-key",
    # sem default: quem nao assinou fica sem a fonte de malha, e o
    # checar_malha.py explica o que preencher. Precisa constar aqui para que
    # a variavel de ambiente real tenha prioridade, como no resto do arquivo.
    "MALHA_API_KEY": "",
    # Horizonte em dias: voo mais distante que isso raramente tem malha
    # publicada e so gastaria cota.
    "MALHA_DIAS": "120",
}


def _ler_ignorados():
    """Localizadores que o sistema nao monitora.

    Ficam fora de tudo - CSV, painel, checagem e alerta - e nao entram na
    contagem de cobertura. Nao sao apagados do MilhasFlow: so nao sao olhados.
    """
    if not os.path.exists(CAMINHO_IGNORADOS):
        return set()
    ignorados = set()
    with open(CAMINHO_IGNORADOS, "r", encoding="utf-8") as f:
        for linha in f:
            codigo = linha.split("#")[0].strip().upper()
            if codigo:
                ignorados.add(codigo)
    return ignorados


def _ler_env():
    valores = dict(PADROES)
    if os.path.exists(CAMINHO_ENV):
        with open(CAMINHO_ENV, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, _, valor = linha.partition("=")
                valores[chave.strip()] = valor.strip().strip('"').strip("'")
    # variaveis de ambiente reais tem prioridade sobre o arquivo
    for chave in list(valores) + list(OBRIGATORIOS):
        if os.environ.get(chave):
            valores[chave] = os.environ[chave]
    return valores


class Config(object):
    def __init__(self):
        v = _ler_env()
        self.email = v.get("MILHASFLOW_EMAIL", "")
        self.senha = v.get("MILHASFLOW_SENHA", "")
        self.anon_key = v.get("MILHASFLOW_ANON_KEY", "")
        self.supabase_url = v.get("SUPABASE_URL", "").rstrip("/")
        self.organization_id = v.get("ORGANIZATION_ID", "")

        # Telegram - unico canal de alerta
        self.telegram_token = v.get("TELEGRAM_TOKEN", "")
        self.telegram_chat = v.get("TELEGRAM_CHAT_ID", "")

        # Malha por numero de voo + data (ver malha.py)
        self.malha_url = v.get("MALHA_API_URL", "").rstrip("/")
        self.malha_header = v.get("MALHA_API_HEADER", "")
        self.malha_key = v.get("MALHA_API_KEY", "")
        try:
            self.malha_dias = int(v.get("MALHA_DIAS") or 120)
        except ValueError:
            self.malha_dias = 120

        # Painel web (site) - projeto Supabase separado do MilhasFlow, so
        # para o site. Vazio = sincronizacao desligada (ver sincronizar_web.py).
        self.supabase_web_url = v.get("SUPABASE_WEB_URL", "").rstrip("/")
        self.supabase_web_service_key = v.get("SUPABASE_WEB_SERVICE_KEY", "")

        # VollyChat - backend separado, ver src/volly_chat.py. Vazio =
        # integracao do chat desligada, resto do sistema roda igual.
        self.chat_url = v.get("CHAT_URL", "").rstrip("/")
        self.chat_anon_key = v.get("CHAT_ANON_KEY", "")
        self.chat_organization_id = v.get("CHAT_ORGANIZATION_ID", "")
        self.chat_refresh_token = v.get("CHAT_REFRESH_TOKEN", "")

        # URL publica do painel (deploy no Vercel). Usada para montar o link
        # "ver no painel" nos alertas do Telegram - ver alertas.link_painel.
        # Vazio = alerta sai sem esse link, resto do sistema roda igual.
        self.painel_web_url = v.get("PAINEL_WEB_URL", "").rstrip("/")

        self.ignorados = _ler_ignorados()

        pasta = v.get("PASTA_DADOS", "dados")
        self.pasta_dados = pasta if os.path.isabs(pasta) else os.path.join(RAIZ, pasta)
        self.caminho_banco = os.path.join(RAIZ, "voos.db")
        self.caminho_tokens = os.path.join(RAIZ, ".tokens.json")
        self.caminho_tokens_chat = os.path.join(RAIZ, ".tokens_chat.json")

    def validar(self):
        """Interrompe com mensagem clara se faltar configuracao."""
        faltando = [c for c in OBRIGATORIOS if not getattr(self, {
            "MILHASFLOW_EMAIL": "email",
            "MILHASFLOW_SENHA": "senha",
            "MILHASFLOW_ANON_KEY": "anon_key",
        }[c])]

        if not os.path.exists(CAMINHO_ENV):
            print("ERRO: arquivo .env nao encontrado.\n")
            print("  Rode:  cp .env.example .env")
            print("  Depois abra o .env e preencha os campos.\n")
            sys.exit(1)

        if faltando:
            print("ERRO: faltam campos no arquivo .env:\n")
            for c in faltando:
                print("  - " + c)
            print("\nAbra o arquivo .env e preencha esses valores.\n")
            sys.exit(1)


config = Config()
