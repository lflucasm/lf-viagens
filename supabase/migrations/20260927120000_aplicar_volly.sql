-- Aplicar na Volly (fase seguinte do fluxo na nuvem, 27/09/2026): a proposta
-- de atualizacao (propostas_volly) ganha o registro de quem pediu pra aplicar,
-- quando foi aplicada e o resultado. Enquanto a chave APLICAR_VOLLY (variavel
-- do GitHub Actions) nao estiver "real", a aplicacao roda em simulacao e so
-- preenche `resultado`.
-- Colar no SQL Editor do Supabase do painel.

alter table public.propostas_volly add column if not exists pedido_em    timestamptz;
alter table public.propostas_volly add column if not exists pedido_por   uuid references public.perfis(id);
alter table public.propostas_volly add column if not exists aplicado_em  timestamptz;
alter table public.propostas_volly add column if not exists resultado    jsonb not null default '{}'::jsonb;
create index if not exists ix_propostas_pedido_por on public.propostas_volly (pedido_por);

-- quem clicou "Aplicar na Volly" (o site so dispara o workflow; o robo le
-- daqui quem pediu). Security definer igual as outras acoes do painel.
create or replace function public.pedir_aplicacao_volly(p_proposta_id bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    update propostas_volly
       set pedido_em = now(), pedido_por = auth.uid()
     where id = p_proposta_id and status = 'proposta';
end;
$$;
revoke all on function public.pedir_aplicacao_volly(bigint) from public;
grant execute on function public.pedir_aplicacao_volly(bigint) to authenticated;
