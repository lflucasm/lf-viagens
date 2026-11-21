-- Suporte pra espelhar o historico do voos.db (SQLite, mantido pelo bot no
-- Mac) pro Supabase sem duplicar em toda rodada de sincronização.
--
-- origem_local_id guarda o id autoincrement do SQLite. UNIQUE simples (não
-- índice parcial): uma constraint UNIQUE já permite qualquer quantidade de
-- NULL (linha criada direto no site, sem origem no SQLite) — e precisa ser
-- uma constraint "de verdade" pro PostgREST conseguir usar
-- `?on_conflict=origem_local_id` no upsert; um índice único parcial não
-- serve de árbitro para ON CONFLICT (coluna) sem repetir o predicado.
alter table public.historico
    add column if not exists origem_local_id bigint;

alter table public.historico
    add constraint historico_origem_local_id_key unique (origem_local_id);
