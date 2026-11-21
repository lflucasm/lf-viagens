-- Guarda o refresh_token GIRATORIO da sessao do MilhasFlow (backend Supabase
-- SEU_PROJETO_MILHASFLOW - ver src/milhasflow.py). Ate 2026-09-15 o login era
-- sempre grant_type=password, mas o MilhasFlow ligou protecao de captcha
-- nesse endpoint (achado na auditoria de 2026-09-14/15: toda rodada do
-- GitHub Actions quebrava com "captcha_failed", porque a maquina e nova a
-- cada execucao e o /tmp/milhasflow_tokens.json local nunca sobrevive entre
-- rodadas - cada uma tentava login por senha de novo e batia no captcha).
--
-- Solucao: mesmo padrao ja usado por chat_auth_state (ver essa migration) -
-- grant_type=refresh_token nao passa pelo captcha, entao guardar o refresh
-- token aqui (compartilhado entre rodada local e cron) deixa a automacao
-- renovar sozinha sem nunca mais precisar do login por senha, contanto que a
-- sessao nao seja revogada.
--
-- Uma linha so, id fixo ('lfviagens') - mesmo esquema de chat_auth_state.
create table if not exists public.milhasflow_auth_state (
    id            text primary key,
    access_token  text,
    refresh_token text not null,
    expira_em     bigint,  -- epoch seconds, mesmo formato de .tokens.json
    updated_at    timestamptz not null default now()
);

-- So o service_role toca aqui (o script roda com SUPABASE_WEB_SERVICE_KEY) -
-- e um token de sessao, nao tem por que nenhum colaborador ler ou escrever
-- direto, nem via RLS de "colaborador ativo".
grant all on public.milhasflow_auth_state to service_role;
alter table public.milhasflow_auth_state enable row level security;
-- Nenhuma policy = ninguem alem de service_role (que ignora RLS) enxerga.
