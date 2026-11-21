-- Vigia FORA do GitHub Actions (15/10/2026).
--
-- Em 15/10/2026 a cota gratis de minutos do Actions acabou as 14:52 UTC e
-- TODAS as automacoes pararam - inclusive o supervisor, que roda no mesmo
-- GitHub e por isso nao tem como avisar que o proprio GitHub parou. Ninguem
-- foi avisado. Alem disso o agendador do GitHub pula rodadas: em 1-15/10 o
-- supervisor "de hora em hora" rodou 63 vezes, com buraco de ate 10,5h.
--
-- Este vigia roda no pg_cron do proprio painel, a cada 15 min, e:
--   1. se o ciclo (.github/workflows/ciclo.yml) nao rodou ha 80 min ou mais,
--      dispara ele pela API do GitHub (no maximo 1x por hora) - cobre o cron
--      que o GitHub pulou;
--   2. se o ciclo ficou 3h sem rodar, ou o supervisor 12h, avisa no
--      Telegram; repete a cada 6h enquanto durar e avisa quando normalizar.
-- O batimento `ingestao` e o pulso do ciclo (primeira etapa dele).
--
-- Segredos ficam no Vault, NUNCA nesta migration (rodar no SQL Editor):
--   select vault.create_secret('<token do bot>',      'telegram_token');
--   select vault.create_secret('<chat id>',           'telegram_chat_id');
--   select vault.create_secret('<token do GitHub>',   'github_dispatch_token');
-- Token do GitHub: fine-grained, so o repositorio lf-viagens, permissao
-- "Actions: Read and write". Sem ele o vigia so avisa (nao dispara); sem o
-- do Telegram so registra em vigia.estado.

create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

-- schema proprio, fora do que o PostgREST expoe: ninguem chama o vigia
-- pela API do site
create schema if not exists vigia;
revoke all on schema vigia from public, anon, authenticated;

create table if not exists vigia.estado (
    chave             text primary key,
    aberto_em         timestamptz,
    ultimo_aviso_em   timestamptz,
    ultimo_disparo_em timestamptz
);

create or replace function vigia.segredo(p_nome text)
returns text language sql stable security definer set search_path = '' as $$
    select decrypted_secret from vault.decrypted_secrets where name = p_nome limit 1;
$$;

-- true = mandou (pg_net e assincrono: "mandou" = pedido enfileirado)
create or replace function vigia.telegram(p_texto text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
    v_token text := vigia.segredo('telegram_token');
    v_chat  text := vigia.segredo('telegram_chat_id');
begin
    if v_token is null or v_chat is null then
        raise notice 'vigia sem Telegram configurado: %', p_texto;
        return false;
    end if;
    perform net.http_post(
        url     := 'https://api.telegram.org/bot' || v_token || '/sendMessage',
        body    := jsonb_build_object('chat_id', v_chat, 'text', p_texto,
                                      'parse_mode', 'HTML',
                                      'disable_web_page_preview', true),
        headers := '{"Content-Type": "application/json"}'::jsonb);
    return true;
end $$;

create or replace function vigia.quando(p_ts timestamptz)
returns text language sql stable set search_path = '' as $$
    select coalesce(to_char(p_ts at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI'), 'nunca');
$$;

-- abre/repete/fecha um alerta de "etapa parada"
-- (o aviso so conta como dado se o Telegram estiver configurado - senao
-- tenta de novo na proxima volta)
create or replace function vigia.avaliar(p_chave text, p_nome text, p_efeito text,
                                         p_ultimo timestamptz, p_limite interval)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_agora    timestamptz := now();
    v_atrasado boolean := p_ultimo is null or v_agora - p_ultimo >= p_limite;
    v_e        vigia.estado;
    v_horas    text := case when p_ultimo is null then '?'
                            else round(extract(epoch from v_agora - p_ultimo) / 3600.0, 1)::text end;
begin
    select * into v_e from vigia.estado where chave = p_chave;
    if v_atrasado then
        if v_e.aberto_em is null or v_agora - v_e.ultimo_aviso_em >= interval '6 hours' then
            if not vigia.telegram(format(
                E'🚨 <b>%s %sparado</b>\nÚltima rodada: %s (há %sh)\n\n%s\nCausas comuns: cota/cobrança do GitHub Actions, erro no workflow, token do disparo vencido.\nhttps://github.com/lflucasm/lf-viagens/actions',
                p_nome, case when v_e.aberto_em is null then '' else 'continua ' end,
                vigia.quando(p_ultimo), v_horas, p_efeito)) then
                return;
            end if;
            insert into vigia.estado (chave, aberto_em, ultimo_aviso_em)
                values (p_chave, v_agora, v_agora)
                on conflict (chave) do update
                set aberto_em = coalesce(vigia.estado.aberto_em, excluded.aberto_em),
                    ultimo_aviso_em = excluded.ultimo_aviso_em;
        end if;
    elsif v_e.aberto_em is not null then
        if not vigia.telegram(format(E'✅ <b>%s voltou a rodar</b>\nAvisado desde %s, última rodada %s',
                                     p_nome, vigia.quando(v_e.aberto_em), vigia.quando(p_ultimo))) then
            return;
        end if;
        update vigia.estado set aberto_em = null where chave = p_chave;
    end if;
end $$;

create or replace function vigia.rodar()
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_agora      timestamptz := now();
    v_ciclo      timestamptz;
    v_supervisor timestamptz;
    v_gh         text := vigia.segredo('github_dispatch_token');
    v_disparo    timestamptz;
begin
    select max(inicio) into v_ciclo      from public.batimentos where etapa = 'ingestao';
    select max(inicio) into v_supervisor from public.batimentos where etapa = 'supervisor';

    -- 1) cron do GitHub pulou o ciclo: dispara (no maximo 1x por hora)
    if v_gh is not null and (v_ciclo is null or v_agora - v_ciclo >= interval '80 minutes') then
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
        v_ciclo, interval '3 hours');
    perform vigia.avaliar('alerta-supervisor', 'Supervisor (GitHub)',
        'Ninguém está conferindo cobertura dos voos, pendências e falhas das etapas.',
        v_supervisor, interval '12 hours');
end $$;

revoke all on all functions in schema vigia from public, anon, authenticated;
revoke all on all tables in schema vigia from public, anon, authenticated;

select cron.unschedule(jobid) from cron.job where jobname = 'vigia-github';
select cron.schedule('vigia-github', '*/15 * * * *', 'select vigia.rodar()');
