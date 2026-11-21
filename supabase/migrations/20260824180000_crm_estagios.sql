-- Estado da automacao de movimentacao de clientes no CRM do MilhasFlow
-- (ver src/mover_crm_cloud.py e docs/superpowers/specs/2026-08-24-automacao-
-- crm-milhasflow-design.md). Guarda o ultimo estagio conhecido de cada
-- cotacao e quando entrou nele - necessario pro timer de 2 dias
-- (Aguardando Feedback -> Concluido) e pra idempotencia (card ja no
-- estagio certo nao repete PATCH nem mensagem de WhatsApp).
create table if not exists public.crm_estagios (
    crm_quote_id text primary key,
    estagio      text not null,
    entrou_em    timestamptz not null default now()
);

-- so o robo (service_role) mexe aqui; nao e dado de colaborador
grant all on public.crm_estagios to service_role;
alter table public.crm_estagios enable row level security;
