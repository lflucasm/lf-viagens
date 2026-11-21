-- Horario da agencia: nada roda no GitHub Actions das 23h as 07h (23/10/2026).
--
-- Pedido do proprietário: a agencia fica ociosa de madrugada, nao precisa gastar
-- minuto nenhum. O vigia (pg_cron, a cada 15 min) passa a ser o agendador
-- de tudo que roda sozinho:
--   ciclo.yml   a cada 2h das 07h as 23h de Brasilia (~07, 09 ... 21h). O
--               supervisor e a ultima etapa dele desde hoje;
--   portais.yml 2 rodadas: manha (07h30, todas as reservas + Azul) e tarde
--               (18h, so quem embarca em ate 7 dias). Uma por janela, sem
--               retentativa; disparo atrasado mais de 3h e descartado.
-- O cron do GitHub saiu desses workflows: atrasava ate 5h (a LATAM "das
-- 07h15" rodava ao meio-dia) e podia cair de madrugada.
--
-- Os avisos de etapa parada tambem so saem das 09h as 23h, que a primeira
-- rodada do dia (07h) tenha tempo de acontecer; de madrugada ficar parado
-- e o esperado.

create or replace function vigia.disparar(p_workflow text, p_inputs jsonb default null)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_gh text := vigia.segredo('github_dispatch_token');
    v_body jsonb := jsonb_build_object('ref', 'main');
begin
    if v_gh is null then
        return;
    end if;
    if p_inputs is not null then
        v_body := v_body || jsonb_build_object('inputs', p_inputs);
    end if;
    perform net.http_post(
        url     := 'https://api.github.com/repos/lflucasm/lf-viagens/actions/workflows/'
                   || p_workflow || '/dispatches',
        body    := v_body,
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || v_gh,
            'Accept', 'application/vnd.github+json',
            'X-GitHub-Api-Version', '2022-11-28',
            'User-Agent', 'lf-viagens-vigia',
            'Content-Type', 'application/json'));
end $$;

create or replace function vigia.marcar_disparo(p_chave text)
returns void language sql security definer set search_path = '' as $$
    insert into vigia.estado (chave, ultimo_disparo_em) values (p_chave, now())
        on conflict (chave) do update set ultimo_disparo_em = excluded.ultimo_disparo_em;
$$;

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

    -- 1) ciclo a cada 2h, so das 07h as 23h (o vigia roda a cada 15 min:
    --    1h50 de folga faz cair no ritmo de 2h). Tenta de novo no maximo 1x
    --    por hora se o disparo anterior nao virou rodada.
    if v_tem_token and v_hora_br between 7 and 22
       and (v_ciclo is null or v_agora - v_ciclo >= interval '110 minutes') then
        select ultimo_disparo_em into v_disparo from vigia.estado where chave = 'disparo-ciclo';
        if v_disparo is null or v_agora - v_disparo >= interval '60 minutes' then
            perform vigia.disparar('ciclo.yml');
            perform vigia.marcar_disparo('disparo-ciclo');
        end if;
    end if;

    -- 2) portais: uma rodada por janela (manha 07h30-10h30, tarde 18h-21h)
    if v_local >= v_hoje_br + interval '7 hours 30 minutes'
       and v_local < v_hoje_br + interval '10 hours 30 minutes' then
        v_rodada := 'manha';
        v_janela := v_hoje_br + interval '7 hours 30 minutes';
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
            v_ciclo, interval '5 hours');
        perform vigia.avaliar('alerta-supervisor', 'Supervisor (GitHub)',
            'Ninguém está conferindo cobertura dos voos, pendências e falhas das etapas.',
            v_supervisor, interval '12 hours');
    end if;
end $$;

revoke all on function vigia.disparar(text, jsonb) from public, anon, authenticated;
revoke all on function vigia.marcar_disparo(text) from public, anon, authenticated;
revoke all on function vigia.rodar() from public, anon, authenticated;
