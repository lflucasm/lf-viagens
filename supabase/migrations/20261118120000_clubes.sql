-- Gestor de clubes: espelho dos clubes da Volly (miles_accounts) + historico de
-- mudancas. A Volly so guarda o estado atual (club_active), entao o historico
-- comeca na 1a rodada de src/clubes_cloud.py (chamada pela ingestao).
create table if not exists public.clubes (
    conta_id       text primary key,            -- miles_accounts.id na Volly
    titular        text not null,
    programa       text not null,               -- 'LATAM Pass', 'Smiles', 'Livelo'...
    ativo          boolean not null default false,
    dia_venc       int,
    custo_mensal   numeric(10,2),
    pontos_mes     int,
    membro_desde   date,
    meses_ativo    int,
    avisado_venc   date,                        -- vencimento ja avisado no Telegram (D-1)
    atualizado_em  timestamptz not null default now()
);
create index if not exists ix_clubes_titular on public.clubes (titular);

create table if not exists public.clubes_eventos (
    id         bigint generated always as identity primary key,
    conta_id   text not null,
    titular    text not null,
    programa   text not null,
    tipo       text not null check (tipo in ('ativou','desativou','custo','pontos','vencimento')),
    de         text,
    para       text,
    em         timestamptz not null default now()
);
create index if not exists ix_clubes_eventos_em on public.clubes_eventos (em desc);

grant all on public.clubes, public.clubes_eventos to service_role;
alter table public.clubes enable row level security;
alter table public.clubes_eventos enable row level security;
drop policy if exists colaborador_le_clubes on public.clubes;
create policy colaborador_le_clubes on public.clubes
    for select to authenticated using ((select eh_colaborador_ativo()));
drop policy if exists colaborador_le_clubes_eventos on public.clubes_eventos;
create policy colaborador_le_clubes_eventos on public.clubes_eventos
    for select to authenticated using ((select eh_colaborador_ativo()));
