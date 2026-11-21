-- Fluxo de monitoramento 100% na nuvem (spec
-- docs/superpowers/specs/2026-09-26-fluxo-monitoramento-voos-nuvem-design.md).
-- Colar no SQL Editor do Supabase do painel (sem acesso DDL pela service key).

-- batimento: uma linha por rodada de cada etapa (supervisor le isso)
create table if not exists public.batimentos (
    id       bigint generated always as identity primary key,
    etapa    text not null,
    inicio   timestamptz not null,
    fim      timestamptz,
    ok       boolean,
    lidos    integer,
    alertas  integer,
    falhas   integer,
    detalhe  jsonb not null default '{}'::jsonb
);
create index if not exists ix_batimentos_etapa_inicio
    on public.batimentos (etapa, inicio desc);

-- trecho que nao da pra checar (sem numero, numero composto, sem fuso)
alter table public.voos add column if not exists incompleto text;

-- fuso aprendido da AeroDataBox pra aeroporto fora do mapa de fusos.py
create table if not exists public.fusos_aeroporto (
    iata      text primary key,
    fuso      text not null,
    visto_em  timestamptz not null default now()
);

-- verificado = resolvido + quem/quando (parte 4)
alter table public.historico add column if not exists verificado_por uuid references public.perfis(id);
alter table public.historico add column if not exists verificado_em  timestamptz;
create index if not exists ix_hist_verificado_por on public.historico (verificado_por);

create table if not exists public.propostas_volly (
    id            bigint generated always as identity primary key,
    voo_id        text not null references public.voos(id),
    historico_id  bigint references public.historico(id),
    status        text not null check (status in
                  ('proposta','sem_proposta','nada_a_mudar','aplicada','descartada')),
    campos        jsonb not null default '{}'::jsonb,   -- {campo: {de, para}}
    fonte         text,
    mensagem      text,
    criado_em     timestamptz not null default now()
);
create index if not exists ix_propostas_voo       on public.propostas_volly (voo_id);
create index if not exists ix_propostas_historico on public.propostas_volly (historico_id);

-- problemas abertos do supervisor + flags simples (ex.: telegram segurado)
create table if not exists public.supervisor_estado (
    chave        text primary key,
    aberto_em    timestamptz,
    avisado_em   timestamptz,
    detalhe      jsonb not null default '{}'::jsonb
);

grant all on public.batimentos, public.fusos_aeroporto, public.propostas_volly,
             public.supervisor_estado to service_role;
alter table public.batimentos        enable row level security;
alter table public.fusos_aeroporto   enable row level security;
alter table public.propostas_volly   enable row level security;
alter table public.supervisor_estado enable row level security;

-- o site le batimentos/propostas/estado (pagina Saude, bloco da proposta)
drop policy if exists colaborador_le_batimentos on public.batimentos;
create policy colaborador_le_batimentos on public.batimentos
    for select to authenticated using ((select eh_colaborador_ativo()));
drop policy if exists colaborador_le_propostas on public.propostas_volly;
create policy colaborador_le_propostas on public.propostas_volly
    for select to authenticated using ((select eh_colaborador_ativo()));
drop policy if exists colaborador_le_supervisor on public.supervisor_estado;
create policy colaborador_le_supervisor on public.supervisor_estado
    for select to authenticated using ((select eh_colaborador_ativo()));

create or replace function public.marcar_historico_verificado(p_historico_id bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    update historico
       set resolvido = true, verificado_por = auth.uid(), verificado_em = now()
     where id = p_historico_id;
end;
$$;
revoke all on function public.marcar_historico_verificado(bigint) from public;
grant execute on function public.marcar_historico_verificado(bigint) to authenticated;

-- liberar alertas segurados pelo teto (parte 3)
create or replace function public.liberar_alertas_segurados()
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    insert into supervisor_estado (chave, aberto_em, detalhe)
    values ('telegram_liberado', now(), '{}'::jsonb)
    on conflict (chave) do update set aberto_em = now();
end;
$$;
revoke all on function public.liberar_alertas_segurados() from public;
grant execute on function public.liberar_alertas_segurados() to authenticated;
