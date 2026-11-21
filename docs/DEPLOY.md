# Deploy — painel web (login + monitoramento de voos)

Checklist pro proprietário rodar depois que o código estiver revisado. Tudo abaixo
precisa de conta/pagamento, por isso não é algo que dá pra automatizar por
aqui.

## 1. Criar o projeto Supabase hospedado

1. Criar conta/projeto em [supabase.com](https://supabase.com) (região São
   Paulo, se disponível).
2. Instalar a CLI local, se ainda não tiver: já usada neste repo via `npx
   supabase`.
3. Linkar o projeto e rodar as migrations:
   ```bash
   npx supabase link --project-ref <ref-do-projeto>
   npx supabase db push
   ```
   Isso aplica `supabase/migrations/*.sql` (schema + RLS + grants) no banco
   hospedado. **Não** rodar `supabase/seed.sql` em produção — ele só existe
   pra dado de teste local.
4. Em **Project Settings → API**, copiar:
   - `Project URL` → vira `NEXT_PUBLIC_SUPABASE_URL`
   - `anon public key` → vira `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `service_role key` → vira `SUPABASE_SERVICE_ROLE_KEY` (secreta, nunca
     vai pro navegador nem pro git)

## 2. Criar o primeiro usuário admin

Direto no painel do Supabase hospedado (**Authentication → Users → Add
user**), criar sua conta com e-mail/senha. Depois, em **SQL Editor**, rodar
(trocando o UUID pelo `id` do usuário criado):

```sql
insert into public.perfis (id, nome, papel, ativo)
values ('<uuid-do-usuario>', 'o proprietário', 'admin', true);
```

Esse passo manual só é necessário para o **primeiro** admin — os próximos
colaboradores são criados pela própria tela `/usuarios` do site.

## 3. Criar o projeto Vercel

1. Importar este repositório no [Vercel](https://vercel.com), apontando o
   **Root Directory** para `web/`.
2. Configurar as env vars do passo 1 (`NEXT_PUBLIC_SUPABASE_URL`,
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) em
   **Project Settings → Environment Variables**.
3. Deploy.
4. Em **Project Settings → Domains**, adicionar o domínio já registrado da
   agência e seguir as instruções de DNS (registro `A`/`CNAME` no provedor
   onde o domínio foi comprado).

## 4. Conferir

- Acessar o domínio, logar com a conta admin criada no passo 2.
- Criar um colaborador de teste em `/usuarios`, confirmar que ele consegue
  logar e que **não** vê `/usuarios`.
- Confirmar que o painel principal carrega (mesmo vazio — o motor de
  checagem ainda não escreve nesse banco, isso é a próxima leva).

## O que ainda não está aqui

A migração do motor de checagem Python (LATAM/GOL/Azul/malha) pro servidor
24/7 é a próxima leva, com plano próprio. Até lá, este site fica com o banco
vazio (ou só com o que for inserido manualmente) — o bot continua rodando no
Mac como hoje, sem publicar aqui ainda.
