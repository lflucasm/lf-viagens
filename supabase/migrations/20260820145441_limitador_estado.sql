-- Estado de ritmo/quarentena pros checadores de nuvem (GitHub Actions, ver
-- src/limitador_cloud.py). Runner de nuvem e descartavel - sem isso, um
-- bloqueio da Azul numa rodada nao seria lembrado na proxima.
create table if not exists public.limitador_estado (
    dominio             text primary key,
    ultima_epoch        double precision,
    marcas              jsonb not null default '[]'::jsonb,
    bloqueado_ate_epoch double precision
);

-- so o motor (service_role) mexe aqui; nao e dado de colaborador
grant all on public.limitador_estado to service_role;
alter table public.limitador_estado enable row level security;
