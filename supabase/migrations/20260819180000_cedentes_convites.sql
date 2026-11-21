-- Área de convite de cedentes — portada do trademiles (lf_viagensTradeM,
-- app/convite/[code] + app/api/convites).
--
-- Diferenças de propósito em relação ao original:
--
--   * lá o cedente entrega as senhas dos programas num formulário só; aqui
--     o cadastro é guiado por etapas (cedente_contas), uma aba por conta, e
--     nenhuma senha é gravada — o que o passo registra é o progresso, não a
--     credencial. Enquanto o fluxo guiado não tiver o texto do PDF, as
--     etapas já nascem criadas e vazias.
--   * lá a página pública fala com o banco via Prisma; aqui ela nunca toca
--     a anon key — /convite/[code] roda em Server Component/Action com
--     service_role, depois de validar o código. Por isso nenhuma destas
--     tabelas tem policy para anon: o acesso público é intermediado.

create table if not exists convites (
    id             uuid primary key default gen_random_uuid(),
    colaborador_id uuid not null unique references perfis(id) on delete cascade,
    codigo         text not null unique,
    ativo          boolean not null default true,
    usos           integer not null default 0,
    ultimo_uso_em  timestamptz,
    criado_em      timestamptz not null default now()
);

-- Termo que o cedente aceita no cadastro. Versionado: o aceite guarda a
-- versão, então mudar o texto não reescreve o que alguém já assinou.
create table if not exists termos_indicacao (
    id            uuid primary key default gen_random_uuid(),
    titulo        text not null,
    slug          text not null unique,
    versao        text not null unique,
    corpo         text not null,
    ordem         integer not null default 0,
    ativo         boolean not null default true,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create table if not exists cedentes (
    id              uuid primary key default gen_random_uuid(),
    identificador   text not null unique,
    nome_completo   text not null,
    data_nascimento date,
    cpf             text not null unique,
    telefone        text,
    email_criado    text,
    banco           text,
    pix_tipo        text check (pix_tipo in ('cpf', 'cnpj', 'email', 'telefone', 'aleatoria')),
    chave_pix       text,
    pontos_latam    integer not null default 0,
    pontos_smiles   integer not null default 0,
    pontos_livelo   integer not null default 0,
    pontos_esfera   integer not null default 0,
    status          text not null default 'pendente'
                    check (status in ('pendente', 'aprovado', 'rejeitado')),
    -- quem convidou. on delete restrict de propósito: desativar colaborador
    -- não pode apagar o cedente que ele trouxe (é dado da agência, não dele)
    colaborador_id  uuid not null references perfis(id) on delete restrict,
    convite_id      uuid references convites(id) on delete set null,
    revisado_por    uuid references perfis(id) on delete set null,
    revisado_em     timestamptz,
    -- preenchido quando o cedente aprovado for empurrado pro MilhasFlow
    milhasflow_id   text,
    -- URL do cadastro guiado (/cedente/<token>): é o que o cedente recebe
    -- pra voltar e continuar de onde parou, sem login
    token_acesso    text not null unique,
    criado_em       timestamptz not null default now(),
    atualizado_em   timestamptz not null default now()
);

create index if not exists cedentes_status_idx      on cedentes (status);
create index if not exists cedentes_colaborador_idx on cedentes (colaborador_id);
create index if not exists cedentes_criado_em_idx   on cedentes (criado_em desc);

create table if not exists aceites_termo (
    id           uuid primary key default gen_random_uuid(),
    cedente_id   uuid not null references cedentes(id) on delete cascade,
    termo_versao text not null,
    ip           text,
    user_agent   text,
    aceito_em    timestamptz not null default now()
);

create index if not exists aceites_termo_cedente_idx on aceites_termo (cedente_id);

-- Uma linha por conta que o cedente precisa criar. É o que a linha do tempo
-- do cadastro guiado lê e escreve — cada aba da tela é uma linha daqui.
create table if not exists cedente_contas (
    id            uuid primary key default gen_random_uuid(),
    cedente_id    uuid not null references cedentes(id) on delete cascade,
    programa      text not null check (programa in ('email', 'latam', 'smiles', 'livelo', 'esfera')),
    ordem         integer not null default 0,
    status        text not null default 'pendente'
                  check (status in ('pendente', 'em_andamento', 'concluida')),
    login         text,
    observacao    text,
    concluida_em  timestamptz,
    atualizado_em timestamptz not null default now(),
    unique (cedente_id, programa)
);

create index if not exists cedente_contas_cedente_idx on cedente_contas (cedente_id);

-- Mesma camada dupla do resto do schema: GRANT primeiro, RLS depois (ver
-- comentário no topo de 20260805205339_rls.sql).
grant select on
    public.convites,
    public.termos_indicacao,
    public.cedentes,
    public.aceites_termo,
    public.cedente_contas
to authenticated;

grant all on
    public.convites,
    public.termos_indicacao,
    public.cedentes,
    public.aceites_termo,
    public.cedente_contas
to service_role;

alter table convites         enable row level security;
alter table termos_indicacao enable row level security;
alter table cedentes         enable row level security;
alter table aceites_termo    enable row level security;
alter table cedente_contas   enable row level security;

-- Colaborador vê o próprio convite; admin vê todos (precisa disso pra
-- desativar código de quem saiu da equipe).
create policy "colaborador le proprio convite" on convites
    for select using (eh_colaborador_ativo() and (colaborador_id = auth.uid() or eh_admin()));

create policy "colaborador le termos" on termos_indicacao
    for select using (eh_colaborador_ativo());

-- Cedente é dado da agência: todo colaborador ativo enxerga a carteira
-- inteira, igual acontece com voos e perfis. Escrita só via service_role.
create policy "colaborador le cedentes" on cedentes
    for select using (eh_colaborador_ativo());
create policy "colaborador le aceites" on aceites_termo
    for select using (eh_colaborador_ativo());
create policy "colaborador le contas do cedente" on cedente_contas
    for select using (eh_colaborador_ativo());
