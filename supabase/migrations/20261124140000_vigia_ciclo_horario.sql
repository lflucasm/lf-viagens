-- Ciclo de hora em hora e portais 3x/dia (24/11/2026).
--
-- O repo do Actions agora e publico (minutos ilimitados), entao o freio de
-- cota de 23/10 (ciclo a cada 2h, portais 2x/dia) cai. Continua valendo o
-- horario da agencia: nada roda entre 23h e 07h (Brasilia).
--   ciclo.yml   a cada hora das 07h as 22h (o vigia roda a cada 15 min:
--               50 min de folga faz cair no ritmo de 1h);
--   portais.yml 3 rodadas: manha (07h30, todas as reservas + Azul), meio-dia
--               (12h30) e tarde (18h), as duas ultimas so quem embarca em
--               ate 7 dias. Uma por janela, sem retentativa.
-- O aviso de ciclo parado cai de 5h para 3h.

create or replace function vigia.rodar()
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_agora      timestamptz := now();
    v_local      timestamp := now() at time zone 'America/Sao_Paulo';
    v_hora_br    int := extract(hour from now() at time zone 'America/Sao_Paulo');
    v_hoje_br    timestamp := date_trunc('day', now() at time zone 'America/Sao_Paulo');
    v_tem_token  boolean := vigia.segredo('github_dispatch_token') is not null;
    v_ciclo      timestamptz;
    v_supervisor timestamptz;
    v_disparo    timestamptz;
    v_rodada     text;
    v_janela     timestamp;
begin
    select max(inicio) into v_ciclo      from public.batimentos where etapa = 'ingestao';
    select max(inicio) into v_supervisor from public.batimentos where etapa = 'supervisor';

    -- 1) ciclo de hora em hora, so das 07h as 23h. Tenta de novo no maximo 1x
    --    a cada 30 min se o disparo anterior nao virou rodada.
    if v_tem_token and v_hora_br between 7 and 22
       and (v_ciclo is null or v_agora - v_ciclo >= interval '50 minutes') then
        select ultimo_disparo_em into v_disparo from vigia.estado where chave = 'disparo-ciclo';
        if v_disparo is null or v_agora - v_disparo >= interval '30 minutes' then
            perform vigia.disparar('ciclo.yml');
            perform vigia.marcar_disparo('disparo-ciclo');
        end if;
    end if;

    -- 2) portais: uma rodada por janela (manha 07h30-10h30, meio-dia
    --    12h30-15h30, tarde 18h-21h). Meio-dia e tarde usam o modo 'tarde'
    --    do workflow (so quem embarca em ate 7 dias, sem Azul).
    if v_local >= v_hoje_br + interval '7 hours 30 minutes'
       and v_local < v_hoje_br + interval '10 hours 30 minutes' then
        v_rodada := 'manha';
        v_janela := v_hoje_br + interval '7 hours 30 minutes';
    elsif v_local >= v_hoje_br + interval '12 hours 30 minutes'
          and v_local < v_hoje_br + interval '15 hours 30 minutes' then
        v_rodada := 'tarde';
        v_janela := v_hoje_br + interval '12 hours 30 minutes';
    elsif v_local >= v_hoje_br + interval '18 hours'
          and v_local < v_hoje_br + interval '21 hours' then
        v_rodada := 'tarde';
        v_janela := v_hoje_br + interval '18 hours';
    end if;
    if v_tem_token and v_rodada is not null then
        select ultimo_disparo_em into v_disparo from vigia.estado where chave = 'disparo-portais';
        if v_disparo is null
           or (v_disparo at time zone 'America/Sao_Paulo') < v_janela then
            perform vigia.disparar('portais.yml', jsonb_build_object('rodada', v_rodada));
            perform vigia.marcar_disparo('disparo-portais');
        end if;
    end if;

    -- 3) avisos de etapa parada, so no horario da agencia
    if v_hora_br between 9 and 22 then
        perform vigia.avaliar('alerta-ciclo', 'Ciclo de conferências (GitHub)',
            'Monitor Volly, reconferência, aplicar, CRM, malha e supervisor não estão rodando.',
            v_ciclo, interval '3 hours');
        perform vigia.avaliar('alerta-supervisor', 'Supervisor (GitHub)',
            'Ninguém está conferindo cobertura dos voos, pendências e falhas das etapas.',
            v_supervisor, interval '12 hours');
    end if;
end $$;

revoke all on function vigia.rodar() from public, anon, authenticated;
