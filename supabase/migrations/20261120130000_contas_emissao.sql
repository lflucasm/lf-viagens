-- Contas LATAM Pass e Smiles espelhadas da Volly (src/turbo_cloud.py) pra tela de
-- sugestao de conta na emissao: saldo, CPFs usados/limite e quando cada CPF volta.
-- Sem CPF do titular (LGPD).
create table if not exists public.contas_emissao (
    conta_id       text primary key,
    titular        text not null,
    programa       text not null,
    saldo          int not null default 0,
    cpm            numeric(10,2),
    clube_ativo    boolean not null default false,
    cpf_usados     int not null default 0,
    cpf_limite     int not null default 25,
    liberacoes     jsonb not null default '[]',
    atualizado_em  timestamptz not null default now()
);
create index if not exists ix_contas_emissao_programa on public.contas_emissao (programa);
grant all on public.contas_emissao to service_role;
alter table public.contas_emissao enable row level security;
drop policy if exists colaborador_le_contas_emissao on public.contas_emissao;
create policy colaborador_le_contas_emissao on public.contas_emissao
    for select to authenticated using ((select eh_colaborador_ativo()));
