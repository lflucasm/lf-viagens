-- Remove o status intermediário "em_andamento" do cadastro guiado: na
-- prática só "ainda não fiz" e "já criei" importavam pro operador, e o meio
-- termo só confundia. Linha que já estava em "em_andamento" volta pra
-- "pendente" -- ela não tem login/senha registrado de qualquer forma
-- (isso só é exigido quando marca como "concluida"), então não perde nada.

update cedente_contas set status = 'pendente' where status = 'em_andamento';

alter table cedente_contas drop constraint if exists cedente_contas_status_check;
alter table cedente_contas add constraint cedente_contas_status_check
    check (status in ('pendente', 'concluida'));
