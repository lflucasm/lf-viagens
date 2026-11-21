-- Dedup do aviso de "vai mover nas proximas 24h" (ver
-- src/mover_crm_cloud.py, planejar_futuro). Mesma ideia de
-- crm_avisos_plano, mas separada porque e um aviso diferente (previa do
-- que vai acontecer amanha, nao do que aconteceu/aconteceria agora) - nao
-- pode compartilhar a mesma chave de dedup, senao o aviso de hoje e o de
-- amanha pra mesma cotacao se apagariam um ao outro. Pedido do proprietário ao
-- ligar o modo real, 2026-08-28.
create table if not exists public.crm_avisos_futuro (
    crm_quote_id text primary key,
    aviso        text not null,
    avisado_em   timestamptz not null default now()
);

grant all on public.crm_avisos_futuro to service_role;
alter table public.crm_avisos_futuro enable row level security;
