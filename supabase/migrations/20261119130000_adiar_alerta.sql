-- Adiar alerta (19/11/2026, ideia tirada da Traveos): tira o alerta da aba
-- Urgente por um tempo SEM resolver. Quando adiado_ate passa, ele volta
-- sozinho. Não mexe em resolvido/notificado: Telegram e supervisor seguem
-- iguais. Colar no SQL Editor do Supabase do painel.

alter table public.historico add column if not exists adiado_ate timestamptz;
alter table public.historico add column if not exists adiado_por uuid references public.perfis(id);
create index if not exists ix_hist_adiado_por on public.historico (adiado_por);

create or replace function public.adiar_historico(p_historico_id bigint, p_horas integer)
returns void language plpgsql security definer set search_path = public as $$
begin
    if not eh_colaborador_ativo() then
        raise exception 'usuario sem perfil ativo';
    end if;
    if p_horas is null or p_horas < 1 or p_horas > 168 then
        raise exception 'adiamento deve ser entre 1 e 168 horas';
    end if;
    update historico
       set adiado_ate = now() + make_interval(hours => p_horas), adiado_por = auth.uid()
     where id = p_historico_id;
end;
$$;
revoke all on function public.adiar_historico(bigint, integer) from public;
grant execute on function public.adiar_historico(bigint, integer) to authenticated;
