-- Corrige o modelo de envio pro MilhasFlow depois de inspecionar o schema
-- real deles (via scripts/descobrir_tabelas_milhasflow.py): a tabela é
-- miles_accounts, e tem UMA LINHA POR CONTA DE PROGRAMA, não uma linha por
-- cedente — quem tem LATAM Pass + Smiles + Livelo vira três linhas lá, cada
-- uma com name/holder_cpf/holder_email repetidos e program/username/password
-- próprios. Por isso o rastro de envio muda de lugar: sai de cedentes (uma
-- linha por titular) e vai para cedente_contas (uma linha por conta), que é
-- o nível certo pra "essa conta específica já subiu".

alter table cedentes drop column if exists milhasflow_enviado_em;
alter table cedentes drop column if exists milhasflow_erro;
alter table cedentes drop column if exists milhasflow_id;

alter table cedente_contas add column if not exists milhasflow_id text;
alter table cedente_contas add column if not exists milhasflow_enviado_em timestamptz;
alter table cedente_contas add column if not exists milhasflow_erro text;
