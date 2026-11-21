-- Gestao do Turbo (Clube LATAM Pass + Turbo, Livelo -> LATAM): espelho da Volly
-- gravado por src/turbo_cloud.py (chamado pela ingestao). Uma linha por conta
-- LATAM com clube (atual ou passado) ou com transferencia Livelo -> LATAM em 12 meses.
-- Sem CPF do titular (LGPD): a ligacao LATAM <-> Livelo e feita na ingestao.
create table if not exists public.turbo (
    conta_id             text primary key,      -- miles_accounts.id (LATAM Pass) na Volly
    titular              text not null,
    status               text,
    clube_ativo          boolean not null default false,
    custo_mensal         numeric(10,2),
    milhas_mes           int,
    dia_venc             int,
    saldo_latam          int not null default 0,
    cpm_latam            numeric(10,2),
    livelo_conta_id      text,
    saldo_livelo         int not null default 0,
    cpm_livelo           numeric(10,2),
    livelo_clube_ativo   boolean not null default false,
    livelo_custo_mensal  numeric(10,2),
    livelo_pontos_mes    int,
    cpf_usados           int not null default 0,
    cpf_limite           int not null default 25,
    liberacoes           jsonb not null default '[]',  -- [{data, qtd}] futuras
    transferencias       jsonb not null default '[]',  -- Livelo -> LATAM, 12 meses, mais recente 1o
    atualizado_em        timestamptz not null default now()
);

grant all on public.turbo to service_role;
alter table public.turbo enable row level security;
drop policy if exists colaborador_le_turbo on public.turbo;
create policy colaborador_le_turbo on public.turbo
    for select to authenticated using ((select eh_colaborador_ativo()));
