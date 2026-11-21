-- "Enviar aviso ao cliente" (20/11/2026): o card da aba Urgente agenda a
-- mensagem pronta na Volly (crm_quote_scheduled_messages, envio em ~1 min)
-- e marca o alerta como verificado. Aqui fica o rastro de quem enviou,
-- quando e o id do agendamento na Volly.
-- Colar no SQL Editor do Supabase do painel.

alter table public.historico add column if not exists aviso_enviado_em  timestamptz;
alter table public.historico add column if not exists aviso_enviado_por uuid references public.perfis(id);
alter table public.historico add column if not exists aviso_volly_id    text;
create index if not exists ix_hist_aviso_enviado_por on public.historico (aviso_enviado_por);

-- Mesmo efeito de marcar_historico_verificado + o rastro do aviso.
create or replace function public.registrar_aviso_cliente(p_historico_id bigint, p_volly_id text)
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    update historico
       set resolvido = true, verificado_por = auth.uid(), verificado_em = now(),
           aviso_enviado_por = auth.uid(), aviso_enviado_em = now(), aviso_volly_id = p_volly_id
     where id = p_historico_id;
end;
$$;
revoke all on function public.registrar_aviso_cliente(bigint, text) from public;
grant execute on function public.registrar_aviso_cliente(bigint, text) to authenticated;
