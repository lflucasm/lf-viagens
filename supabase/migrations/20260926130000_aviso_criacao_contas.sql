-- Etapa de aviso entre o PIX/termo e a criação de contas de fato. Muitos
-- cedentes estavam pulando direto pra aba de cada programa e digitando
-- qualquer login/senha, sem de fato abrir o site e criar a conta. Esse
-- timestamp marca que o cedente já viu o aviso e confirmou que vai criar
-- as contas de verdade antes de a gente mostrar o passo a passo — ver
-- app/cedente/[token]/AvisoContas.tsx.
alter table cedentes add column if not exists aviso_contas_confirmado_em timestamptz;
