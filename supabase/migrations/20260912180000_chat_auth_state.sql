-- Guarda o refresh_token GIRATORIO da sessao do VollyChat (backend Supabase
-- separado, federado por SSO/OTP - ver src/volly_chat.py). Cada uso do
-- refresh_token invalida o anterior e devolve um novo; como o GitHub
-- Actions nao mantem estado entre execucoes (maquina nova a cada rodada),
-- o token giratorio PRECISA morar num lugar durável e compartilhado entre
-- rodada manual (local) e cron (nuvem) - senao quem rodar por ultimo
-- invalida o token de quem rodar depois.
--
-- Uma linha so, id fixo ('lfviagens') - nao e por usuario nem por
-- organizacao, e o estado de UMA sessao federada.
create table if not exists chat_auth_state (
    id            text primary key,
    access_token  text,
    refresh_token text not null,
    expira_em     bigint,  -- epoch seconds, mesmo formato de .tokens_chat.json
    updated_at    timestamptz not null default now()
);

-- So o service_role toca aqui (o script roda com SUPABASE_WEB_SERVICE_KEY) -
-- e um token de sessao, nao tem por que nenhum colaborador ler ou escrever
-- direto, nem via RLS de "colaborador ativo".
grant all on public.chat_auth_state to service_role;
alter table chat_auth_state enable row level security;
-- Nenhuma policy = ninguem alem de service_role (que ignora RLS) enxerga.
