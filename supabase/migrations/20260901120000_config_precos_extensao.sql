-- Config da camada de preço da extensão (ver docs/superpowers/specs/
-- 2026-08-30-extensao-preco-milhas-fase1-design.md). A extensão injeta o custo
-- em R$ dos voos em milhas; o R$/milheiro padrão vem da média por faixa do
-- felip-ai (GET /market/internal/price-bands), e estas tabelas guardam os
-- ajustes que o colaborador faz por cima:
--
--   1. config_precos_extensao  - override manual de R$/milheiro por programa,
--      que VENCE a média de mercado quando preenchido.
--   2. config_markup_extensao  - o markup (linha única) aplicado sobre o custo
--      pra virar preço de venda no orçamento.
--
-- São editadas pelo colaborador logado (JWT do Supabase que a extensão manda
-- pras rotas /api/extensao/*), então têm policy pra `authenticated`, diferente
-- das tabelas do motor que só o service_role toca. São minúsculas (uma linha
-- por programa + uma de markup) - nada de índice além da PK.

-- ── Override de R$/milheiro por programa ────────────────────────────────────
create table if not exists public.config_precos_extensao (
    -- Nome do programa como o felip-ai devolve: 'LATAM', 'SMILES',
    -- 'AZUL/TUDO AZUL', 'AZUL PELO MUNDO'. Não é FK - o felip-ai é outro banco.
    programa        text primary key,
    -- null = sem override, usa a média de mercado. > 0 quando o colaborador
    -- fixa o valor à mão.
    milheiro_manual numeric check (milheiro_manual is null or milheiro_manual > 0),
    atualizado_em   timestamptz not null default now(),
    atualizado_por  uuid references public.perfis(id) on delete set null
);

-- ── Markup do orçamento (linha única) ──────────────────────────────────────
create table if not exists public.config_markup_extensao (
    -- Trava de linha única: só `true` é aceito na PK, então nunca há uma
    -- segunda linha pra divergir.
    id             boolean primary key default true check (id),
    tipo           text not null default 'pct' check (tipo in ('pct', 'abs')),
    -- Percentual quando tipo = 'pct'; reais quando 'abs'. 0 = markup desligado.
    valor          numeric not null default 0 check (valor >= 0),
    -- 'venda' soma o markup fixo uma vez por venda; 'pessoa', uma vez por pax.
    -- A Fase 1 só usa 'venda', mas a coluna já aceita os dois.
    escopo         text not null default 'venda' check (escopo in ('venda', 'pessoa')),
    atualizado_em  timestamptz not null default now(),
    atualizado_por uuid references public.perfis(id) on delete set null
);

insert into public.config_markup_extensao (id) values (true) on conflict do nothing;

-- ── Grants + RLS ──────────────────────────────────────────────────────────
-- GRANT antes de RLS: tabela criada por migration não ganha privilégio
-- nenhum pros papéis por padrão (mesma nota do 20260805205339_rls.sql).
grant select, insert, update on public.config_precos_extensao to authenticated;
grant select, insert, update on public.config_markup_extensao  to authenticated;
grant all on public.config_precos_extensao to service_role;
grant all on public.config_markup_extensao  to service_role;

alter table public.config_precos_extensao enable row level security;
alter table public.config_markup_extensao  enable row level security;

-- Colaborador ativo lê e escreve; sem delete (config não se apaga, só zera).
create policy "colaborador le config precos" on public.config_precos_extensao
    for select using (eh_colaborador_ativo());
create policy "colaborador grava config precos" on public.config_precos_extensao
    for insert with check (eh_colaborador_ativo());
create policy "colaborador atualiza config precos" on public.config_precos_extensao
    for update using (eh_colaborador_ativo()) with check (eh_colaborador_ativo());

create policy "colaborador le config markup" on public.config_markup_extensao
    for select using (eh_colaborador_ativo());
create policy "colaborador grava config markup" on public.config_markup_extensao
    for insert with check (eh_colaborador_ativo());
create policy "colaborador atualiza config markup" on public.config_markup_extensao
    for update using (eh_colaborador_ativo()) with check (eh_colaborador_ativo());
