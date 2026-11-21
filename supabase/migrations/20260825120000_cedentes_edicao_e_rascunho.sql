-- Duas mudanças no fluxo de cedentes:
--
--   * "rascunho": a Fase 1 (dados pessoais, /convite/[code]) deixa de ser
--     tudo-ou-nada. O titular preenche nome/CPF/nascimento/telefone, o
--     cedente já nasce no banco (status rascunho) com o token_acesso — o
--     mesmo link de /cedente/[token] que já servia pra retomar a Fase 2
--     passa a servir pra retomar a Fase 1 também. Sem isso, sair da página
--     antes do fim perdia tudo (não tinha onde retomar).
--
--   * "ativo": exclusão de cadastro é inativação, não delete físico — seguindo
--     o mesmo padrão já usado em perfis.ativo e convites.ativo. Mantém o
--     histórico (aceite de termo, contas criadas) em vez de apagar.

alter table cedentes drop constraint if exists cedentes_status_check;
alter table cedentes add constraint cedentes_status_check
    check (status in ('rascunho', 'pendente', 'aprovado', 'rejeitado'));

alter table cedentes add column if not exists ativo boolean not null default true;
create index if not exists cedentes_ativo_idx on cedentes (ativo);
