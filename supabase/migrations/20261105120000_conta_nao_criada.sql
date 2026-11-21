-- Esfera é a única conta que o cedente pode declarar que não conseguiu criar
-- (o cadastro dela costuma barrar por telefone/CPF). "nao_criada" é diferente
-- de "pendente": pendente = ainda não fez; nao_criada = tentou e desistiu, e o
-- cadastro segue para a cartilha sem ela. Ver marcarContaNaoCriada() em
-- web/app/cedente/[token]/actions.ts.

alter table cedente_contas drop constraint if exists cedente_contas_status_check;
alter table cedente_contas add constraint cedente_contas_status_check
    check (status in ('pendente', 'concluida', 'nao_criada'));
