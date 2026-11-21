-- Schema do painel web de monitoramento de voos.
--
-- As tabelas voos/historico/observacoes/execucoes/malha_checagens/malha_cota
-- espelham o schema do SQLite local (src/db.py) de propósito — a próxima
-- leva porta o motor Python pra escrever aqui em vez de voos.db, e manter os
-- mesmos nomes/colunas reduz a distância entre os dois.
--
-- embarque/chegada ficam TEXT (não timestamptz): guardam o horário LOCAL do
-- aeroporto de propósito (ver README raiz, seção "fusos") — converter pra
-- timestamptz forçaria um fuso único e reintroduziria o bug de "horário
-- alterado" em 100% dos voos que o sistema já teve e corrigiu.

create table if not exists voos (
    id              text primary key,
    emissao_id      text,
    localizador     text,
    cia             text,
    numero_voo      text,
    origem          text,
    destino         text,
    embarque        text,
    chegada         text,
    classe          text,
    sentido         text,
    status          text,
    cliente         text,
    passageiros     text,
    tags            text,
    balcao          integer not null default 0,
    valor_venda     numeric,
    ativo           boolean not null default true,
    visto_em        timestamptz,
    criado_em       timestamptz not null default now()
);

create table if not exists perfis (
    id         uuid primary key references auth.users(id) on delete cascade,
    nome       text not null,
    papel      text not null default 'atendente' check (papel in ('admin', 'atendente')),
    ativo      boolean not null default true,
    criado_em  timestamptz not null default now()
);

-- Uma alteração/cancelamento detectado. resolvido + atendente_id são o que
-- o spec chama de "alertas" — é a mesma tabela do historico do motor, só com
-- as duas colunas que o painel de triagem precisa.
create table if not exists historico (
    id            bigint generated always as identity primary key,
    voo_id        text not null references voos(id),
    evento        text not null,     -- novo | alterado | sumiu | reapareceu
    campo         text,
    valor_antigo  text,
    valor_novo    text,
    origem        text not null,     -- milhasflow | portal | malha
    detectado_em  timestamptz not null default now(),
    notificado    boolean not null default false,
    resolvido     boolean not null default false,
    atendente_id  uuid references perfis(id)
);

create table if not exists execucoes (
    id            bigint generated always as identity primary key,
    executado_em  timestamptz not null default now(),
    voos_lidos    integer,
    novos         integer,
    alterados     integer,
    sumiram       integer,
    erro          text
);

create table if not exists malha_checagens (
    chave  text primary key,   -- "numero_voo|AAAA-MM-DD"
    ultima timestamptz not null,
    vezes  integer not null default 1
);

create table if not exists malha_cota (
    id         integer primary key check (id = 1),
    restantes  integer,
    limite     integer,
    reset_em   timestamptz,
    visto_em   timestamptz not null
);

-- O que cada fonte viu por último em cada voo — uma linha por voo x fonte,
-- não histórico. É o que permite dizer "duas fontes confirmam" ou
-- "fontes divergem" (ver README, seção "Duas fontes discordando").
create table if not exists observacoes (
    voo_id    text not null references voos(id),
    origem    text not null,      -- portal-latam | portal-gol | portal-azul | malha
    partida   text,               -- "AAAA-MM-DD HH:MM", hora LOCAL do aeroporto
    rota      text,               -- "REC-GRU"
    situacao  text,               -- confirmado | cancelado | ...
    visto_em  timestamptz not null default now(),
    primary key (voo_id, origem)
);

-- Espelha links_reservas.json (src/indexar_links.py). Alimentada pelo Mac na
-- próxima leva; por enquanto só existe o schema.
create table if not exists links_pdf (
    localizador     text primary key,
    pedido          text,
    companhia       text,
    sobrenome       text,
    origem          text,
    util            boolean,
    arquivo         text,
    url             text,
    atualizado_em   timestamptz not null default now()
);

-- Substitui os pendencias_<cia>.json/.csv gerados por cada conector.
create table if not exists pendencias (
    id          bigint generated always as identity primary key,
    cia         text not null,
    localizador text not null,
    motivo      text,
    criado_em   timestamptz not null default now(),
    unique (cia, localizador)
);

create table if not exists notas (
    id         bigint generated always as identity primary key,
    voo_id     text not null references voos(id),
    autor_id   uuid not null references perfis(id),
    texto      text not null,
    criado_em  timestamptz not null default now()
);

create index if not exists ix_hist_voo        on historico(voo_id);
create index if not exists ix_hist_data       on historico(detectado_em);
create index if not exists ix_hist_resolvido  on historico(resolvido);
create index if not exists ix_voos_emb        on voos(embarque);
create index if not exists ix_notas_voo       on notas(voo_id);
create index if not exists ix_pendencias_cia  on pendencias(cia);
