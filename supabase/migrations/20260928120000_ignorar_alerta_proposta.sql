-- Ignorar alerta e ignorar proposta (pedido do proprietário em 28/09/2026): tanto a
-- verificacao quanto a aplicacao na Volly sao opcionais. Ignorar tira o
-- alerta da aba Urgente (ou a proposta da fila) SEM reconferir nem gravar
-- nada na Volly, e registra quem ignorou e quando.
-- Colar no SQL Editor do Supabase do painel.

alter table public.historico add column if not exists ignorado_por uuid references public.perfis(id);
alter table public.historico add column if not exists ignorado_em  timestamptz;
create index if not exists ix_hist_ignorado_por on public.historico (ignorado_por);

alter table public.propostas_volly add column if not exists descartado_por uuid references public.perfis(id);
alter table public.propostas_volly add column if not exists descartado_em  timestamptz;
create index if not exists ix_propostas_descartado_por on public.propostas_volly (descartado_por);

create or replace function public.ignorar_historico(p_historico_id bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    update historico
       set resolvido = true, ignorado_por = auth.uid(), ignorado_em = now()
     where id = p_historico_id;
end;
$$;
revoke all on function public.ignorar_historico(bigint) from public;
grant execute on function public.ignorar_historico(bigint) to authenticated;

create or replace function public.descartar_proposta_volly(p_proposta_id bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    update propostas_volly
       set status = 'descartada', descartado_por = auth.uid(), descartado_em = now()
     where id = p_proposta_id and status = 'proposta';
end;
$$;
revoke all on function public.descartar_proposta_volly(bigint) from public;
grant execute on function public.descartar_proposta_volly(bigint) to authenticated;
