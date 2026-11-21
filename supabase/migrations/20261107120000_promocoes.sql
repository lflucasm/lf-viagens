-- Promocoes de milhas/pontos lidas dos grupos fechados do Telegram
-- (src/checar_promocoes_cloud.py). A IA so extrai; custo por milheiro e
-- resumo sao calculados em codigo (src/promocoes.py). A aba "Promocoes ativas"
-- do site mostra as que ainda nao acabaram (fim nulo ou no futuro).
create table if not exists public.promocoes (
    id             text primary key,            -- hash de programa+tipo+fim+bonus (repost cai na mesma)
    programa       text not null,
    tipo           text not null check (tipo in
                   ('compra_pontos','transferencia_bonificada','clube','resgate','outro')),
    inicio         timestamptz,
    fim            timestamptz,
    dados          jsonb not null default '{}'::jsonb,   -- extracao crua da IA
    cenarios       jsonb not null default '[]'::jsonb,   -- custo final por plano (codigo)
    resumo         text not null,                        -- HTML do Telegram
    oportunidade   boolean not null default false,       -- abaixo do teto do programa
    fonte          text,
    mensagem_url   text,
    avisado_em     timestamptz,                          -- 1o aviso no canal de clubes
    aviso_fim_em   timestamptz,                          -- aviso de 24h antes de acabar
    criado_em      timestamptz not null default now()
);
create index if not exists ix_promocoes_fim on public.promocoes (fim);

grant all on public.promocoes to service_role;
alter table public.promocoes enable row level security;
drop policy if exists colaborador_le_promocoes on public.promocoes;
create policy colaborador_le_promocoes on public.promocoes
    for select to authenticated using ((select eh_colaborador_ativo()));
