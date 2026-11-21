-- Convite público passa a terminar no nome de quem indicou, não num código
-- aleatório (ex.: /convite/PauloHenrique em vez de /convite/M4JC28WR) — fica
-- claro pra quem recebe quem mandou o link. gerarCodigoConvite() em
-- web/lib/cedentes.ts já gera assim pra convites novos (ver
-- app/(painel)/cedentes/actions.ts); esta migração só normaliza os convites
-- que já existiam antes da mudança.

do $$
declare
  linha        record;
  base         text;
  tentativa    int;
  codigo_final text;
begin
  for linha in select c.id, p.nome from convites c join perfis p on p.id = c.colaborador_id loop
    -- tira os acentos comuns em nomes em português, descarta o que não for
    -- letra/número/espaço e capitaliza cada palavra antes de juntar
    base := translate(
      linha.nome,
      'áàâãäåāăąÁÀÂÃÄÅĀĂĄéèêëēĕėęěÉÈÊËĒĔĖĘĚíìîïĩīĭįıÍÌÎÏĨĪĬĮİóòôõöøōŏőÓÒÔÕÖØŌŎŐúùûüũūŭůűųÚÙÛÜŨŪŬŮŰŲçćĉċčÇĆĈĊČñńņňÑŃŅŇ',
      'aaaaaaaaaAAAAAAAAAeeeeeeeeeEEEEEEEEEiiiiiiiiiIIIIIIIIIooooooooOOOOOOOOuuuuuuuuuUUUUUUUUcccccCCCCCnnnnNNNN'
    );
    base := regexp_replace(base, '[^a-zA-Z0-9 ]+', '', 'g');
    base := array_to_string(
      array(select initcap(w) from unnest(regexp_split_to_array(trim(base), '\s+')) as w where w <> ''),
      ''
    );
    if base = '' then
      base := 'Colaborador';
    end if;

    tentativa := 0;
    loop
      codigo_final := case when tentativa = 0 then base else base || (tentativa + 1)::text end;
      exit when not exists (
        select 1 from convites c2 where c2.codigo = codigo_final and c2.id <> linha.id
      );
      tentativa := tentativa + 1;
    end loop;

    update convites set codigo = codigo_final where id = linha.id;
  end loop;
end $$;
