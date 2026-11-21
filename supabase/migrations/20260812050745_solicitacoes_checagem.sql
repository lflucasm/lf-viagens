-- Fila de checagens sob demanda: o colaborador pede pelo botão "Checar
-- agora" no painel, e quem atende depende da companhia (ver
-- src/atender_solicitacoes.py, que roda no Mac pra LATAM/GOL/Azul - malha
-- não passa por aqui, o botão dispara o GitHub Actions direto).
--
-- Só o colaborador dono lê/cria a própria solicitação, e só service_role
-- (o script que atende) marca como concluída - mesma separação leitura x
-- escrita do resto do schema (ver 20260805205339_rls.sql).
create table if not exists solicitacoes_checagem (
    id             bigint generated always as identity primary key,
    voo_id         text not null references voos(id),
    localizador    text not null,
    cia            text,
    solicitado_por uuid references perfis(id),
    solicitado_em  timestamptz not null default now(),
    status         text not null default 'pendente'
                       check (status in ('pendente', 'concluida', 'erro')),
    concluido_em   timestamptz,
    resultado      text
);

-- O poller do Mac varre "quem esta pendente" a cada poucos minutos - sem
-- indice isso vira table scan a cada rodada.
create index if not exists ix_solicitacoes_status on solicitacoes_checagem(status);
-- FK sem indice = JOIN e CASCADE lentos (Postgres nao indexa FK sozinho) -
-- mesmo padrao de ix_hist_voo em historico.
create index if not exists ix_solicitacoes_voo on solicitacoes_checagem(voo_id);

grant select, insert on public.solicitacoes_checagem to authenticated;
grant all on public.solicitacoes_checagem to service_role;

alter table solicitacoes_checagem enable row level security;

-- (select ...) em vez de chamar a funcao direto: sem isso o Postgres reavalia
-- auth.uid()/eh_colaborador_ativo() LINHA A LINHA em vez de uma vez so por
-- query (ver supabase-postgres-best-practices, security-rls-performance).
create policy "colaborador le solicitacoes" on solicitacoes_checagem
    for select using ((select eh_colaborador_ativo()));

create policy "colaborador cria solicitacao" on solicitacoes_checagem
    for insert with check (
        solicitado_por = (select auth.uid()) and (select eh_colaborador_ativo())
    );
