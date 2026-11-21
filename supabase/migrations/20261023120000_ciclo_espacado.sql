-- Ciclo espacado: a cada 2h de dia, a cada 4h de madrugada (23/10/2026).
--
-- Com o ciclo de hora em hora, outubro projetava ~2.200 min cobrados no
-- GitHub Actions (cota gratis de 2.000, repositorio privado) e o ciclo era
-- 61% disso: ~18 rodadas/dia de ~2,3 min. E o agendador do GitHub so
-- entregava ~5 das 24 rodadas por dia; as outras 99 de 138 (16-22/10) ja
-- eram disparadas por este vigia.
--
-- Agora o vigia e o UNICO agendador do ciclo (o `schedule` saiu do
-- ciclo.yml - com os dois, rodada atrasada do GitHub chegando depois do
-- disparo daqui virava rodada dobrada, cobrada inteira):
--   07h-23h (Brasilia): dispara quando o ultimo ciclo tem 1h50 ou mais
--   23h-07h:            dispara quando o ultimo ciclo tem 3h50 ou mais
-- (o vigia roda a cada 15 min, entao 10 min de folga faz cair no ritmo).
-- Da ~10 rodadas por dia: ~7, 9, 11, 13, 15, 17, 19, 21, 01 e 05h.
--
-- O aviso de ciclo parado passa de 3h pra 5h (cobre a janela de 4h da
-- madrugada sem alarme falso).

create or replace function vigia.rodar()
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_agora      timestamptz := now();
    v_hora_br    int := extract(hour from now() at time zone 'America/Sao_Paulo');
    v_intervalo  interval := case when v_hora_br between 7 and 22
                                  then interval '110 minutes'
                                  else interval '230 minutes' end;
    v_ciclo      timestamptz;
    v_supervisor timestamptz;
    v_gh         text := vigia.segredo('github_dispatch_token');
    v_disparo    timestamptz;
begin
    select max(inicio) into v_ciclo      from public.batimentos where etapa = 'ingestao';
    select max(inicio) into v_supervisor from public.batimentos where etapa = 'supervisor';

    -- 1) hora do ciclo: dispara (e tenta de novo no maximo 1x por hora se o
    --    disparo anterior nao virou rodada)
    if v_gh is not null and (v_ciclo is null or v_agora - v_ciclo >= v_intervalo) then
        select ultimo_disparo_em into v_disparo from vigia.estado where chave = 'disparo-ciclo';
        if v_disparo is null or v_agora - v_disparo >= interval '60 minutes' then
            perform net.http_post(
                url     := 'https://api.github.com/repos/lflucasm/lf-viagens/actions/workflows/ciclo.yml/dispatches',
                body    := '{"ref": "main"}'::jsonb,
                headers := jsonb_build_object(
                    'Authorization', 'Bearer ' || v_gh,
                    'Accept', 'application/vnd.github+json',
                    'X-GitHub-Api-Version', '2022-11-28',
                    'User-Agent', 'lf-viagens-vigia',
                    'Content-Type', 'application/json'));
            insert into vigia.estado (chave, ultimo_disparo_em) values ('disparo-ciclo', v_agora)
                on conflict (chave) do update set ultimo_disparo_em = excluded.ultimo_disparo_em;
        end if;
    end if;

    -- 2) avisos de etapa parada
    perform vigia.avaliar('alerta-ciclo', 'Ciclo de conferências (GitHub)',
        'Monitor Volly, reconferência, aplicar, CRM e malha não estão rodando.',
        v_ciclo, interval '5 hours');
    perform vigia.avaliar('alerta-supervisor', 'Supervisor (GitHub)',
        'Ninguém está conferindo cobertura dos voos, pendências e falhas das etapas.',
        v_supervisor, interval '12 hours');
end $$;

revoke all on function vigia.rodar() from public, anon, authenticated;
