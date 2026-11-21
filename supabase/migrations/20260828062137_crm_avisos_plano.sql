-- Dedup dos avisos de Telegram da automacao de CRM (ver
-- src/mover_crm_cloud.py, crm_regras.selecionar_novidades). Sem isso, como
-- o --plano nunca escreve nada no board do Volly, o mesmo "moveria Fulano
-- de X pra Y" (ou a mesma pendencia/erro) seria recalculado e reenviado
-- pro Telegram a cada rodada do cron (2/2h) pra sempre - so avisa quando o
-- que seria feito mudou desde o ultimo aviso. Pedido do proprietário, 2026-08-28.
create table if not exists public.crm_avisos_plano (
    crm_quote_id text primary key,
    aviso        text not null,
    avisado_em   timestamptz not null default now()
);

-- so o robo (service_role) mexe aqui; nao e dado de colaborador
grant all on public.crm_avisos_plano to service_role;
alter table public.crm_avisos_plano enable row level security;
