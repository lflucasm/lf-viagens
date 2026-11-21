-- RLS: colaborador autenticado e ativo lê os dados de monitoramento;
-- escrita dos dados do motor (voos/historico/observacoes/execucoes/
-- malha_*/links_pdf/pendencias) só acontece via service_role, que ignora
-- RLS por padrão no Supabase — por isso essas tabelas não têm policy de
-- insert/update para o papel authenticated, de propósito.
--
-- Duas ações do painel mudam dado protegido (historico.resolvido,
-- historico.atendente_id): passam por função SECURITY DEFINER em vez de
-- UPDATE direto, porque RLS do Postgres não restringe por coluna.
--
-- GRANT antes de RLS: tabela criada por migration SQL (fora da Studio UI)
-- não ganha privilégio nenhum pros papéis anon/authenticated/service_role
-- por padrão — sem o GRANT, toda query cai em "permission denied" antes
-- mesmo da RLS ser avaliada. service_role ignora RLS (BYPASSRLS), mas
-- BYPASSRLS não dispensa o GRANT de tabela — são duas camadas diferentes,
-- e as duas precisam estar liberadas.
grant usage on schema public to authenticated, service_role;

grant select on
    public.voos,
    public.historico,
    public.observacoes,
    public.execucoes,
    public.malha_checagens,
    public.malha_cota,
    public.links_pdf,
    public.pendencias,
    public.perfis
to authenticated;

grant select, insert on public.notas to authenticated;
grant update on public.perfis to authenticated;

-- service_role é o motor de checagem (próxima leva) e as Server Actions
-- administrativas do site — precisa de leitura e escrita em tudo.
grant all on
    public.voos,
    public.historico,
    public.observacoes,
    public.execucoes,
    public.malha_checagens,
    public.malha_cota,
    public.links_pdf,
    public.pendencias,
    public.perfis,
    public.notas
to service_role;

grant usage, select on all sequences in schema public to service_role;

create or replace function public.eh_colaborador_ativo()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1 from perfis where id = auth.uid() and ativo
    );
$$;

create or replace function public.eh_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1 from perfis where id = auth.uid() and ativo and papel = 'admin'
    );
$$;

alter table voos            enable row level security;
alter table historico        enable row level security;
alter table observacoes      enable row level security;
alter table execucoes        enable row level security;
alter table malha_checagens  enable row level security;
alter table malha_cota       enable row level security;
alter table links_pdf        enable row level security;
alter table pendencias       enable row level security;
alter table notas            enable row level security;
alter table perfis           enable row level security;

create policy "colaborador le voos"           on voos           for select using (eh_colaborador_ativo());
create policy "colaborador le historico"      on historico      for select using (eh_colaborador_ativo());
create policy "colaborador le observacoes"    on observacoes    for select using (eh_colaborador_ativo());
create policy "colaborador le execucoes"      on execucoes      for select using (eh_colaborador_ativo());
create policy "colaborador le malha_checagens" on malha_checagens for select using (eh_colaborador_ativo());
create policy "colaborador le malha_cota"     on malha_cota     for select using (eh_colaborador_ativo());
create policy "colaborador le links_pdf"      on links_pdf      for select using (eh_colaborador_ativo());
create policy "colaborador le pendencias"     on pendencias     for select using (eh_colaborador_ativo());

create policy "colaborador le notas" on notas
    for select using (eh_colaborador_ativo());
create policy "colaborador cria propria nota" on notas
    for insert with check (autor_id = auth.uid() and eh_colaborador_ativo());

-- Qualquer colaborador ativo vê o time inteiro (nome/papel/ativo) — precisa
-- disso pra filtrar por atendente e pra atribuir pendência a um colega, não
-- só o admin. Só admin pode alterar (criar/desativar/trocar papel).
create policy "colaborador le perfis" on perfis
    for select using (eh_colaborador_ativo());
create policy "admin atualiza perfis" on perfis
    for update using (eh_admin()) with check (eh_admin());

create or replace function public.marcar_historico_resolvido(p_historico_id bigint, p_resolvido boolean)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;

    update historico set resolvido = p_resolvido where id = p_historico_id;
end;
$$;

create or replace function public.atribuir_historico(p_historico_id bigint, p_atendente_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;

    if p_atendente_id is not null and not exists (
        select 1 from perfis where id = p_atendente_id and ativo
    ) then
        raise exception 'atendente informado nao existe ou esta inativo';
    end if;

    update historico set atendente_id = p_atendente_id where id = p_historico_id;
end;
$$;

revoke all on function public.marcar_historico_resolvido(bigint, boolean) from public;
revoke all on function public.atribuir_historico(bigint, uuid) from public;
grant execute on function public.marcar_historico_resolvido(bigint, boolean) to authenticated;
grant execute on function public.atribuir_historico(bigint, uuid) to authenticated;
