-- Historico de pulsos de gestao (src/relatorio_gestao.py) - substitui o MCP
-- pago da Volly: le direto no Supabase deles (src/volly.py), calcula os
-- KPIs em Python (src/gestao.py) e grava aqui o snapshot completo, pra uma
-- pagina do painel mostrar sem recalcular nada nem gastar credito.
--
-- Append-only (1 linha por rodada, nao upsert) - assim da pra comparar
-- pulso com pulso depois, mesmo padrao de `historico` pros voos.
create table if not exists gestao_relatorios (
    id         bigint generated always as identity primary key,
    gerado_em  date not null,
    dados      jsonb not null,
    criado_em  timestamptz not null default now()
);

create index if not exists ix_gestao_relatorios_gerado_em
    on gestao_relatorios(gerado_em desc);

-- Escrita e so do script (roda com SUPABASE_WEB_SERVICE_KEY, fora do RLS).
-- Leitura e so pra colaborador logado no painel - mesma regra do resto do
-- schema (ver 20260805205339_rls.sql).
grant select on public.gestao_relatorios to authenticated;
grant all on public.gestao_relatorios to service_role;

alter table gestao_relatorios enable row level security;

create policy "colaborador le relatorios de gestao" on gestao_relatorios
    for select using ((select eh_colaborador_ativo()));
