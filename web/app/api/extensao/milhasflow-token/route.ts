import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { exigirColaboradorPorToken } from "../_auth";

/**
 * POST /api/extensao/milhasflow-token
 * body: { access_token?: string, refresh_token: string, expira_em?: number }
 *
 * Recebe o token de sessão do MilhasFlow (backend Supabase
 * SEU_PROJETO_MILHASFLOW - ver src/milhasflow.py) que o content script
 * `content-milhasflow-token.js` capta do localStorage sempre que a aba do
 * navegador renova sozinha. Grava em milhasflow_auth_state pra
 * checar_latam_cloud.py / mover_crm_cloud.py / checar_gol_cloud.py
 * (rodando local ou no GitHub Actions) lerem dali.
 *
 * Existe pro mesmo motivo do chat-token: MilhasFlow ligou captcha no login
 * por senha (14/09/2026) e o refresh_token é giratório (uso único) - se o
 * robô perder o valor mais recente (ex: rodadas concorrentes disputando o
 * mesmo token), a única forma de renovar sem depender de alguém copiar
 * token do DevTools na mão é ter esta aba, que já renova sozinha no dia a
 * dia, publicando o valor fresco aqui.
 *
 * `milhasflow_auth_state` nao tem policy de RLS pra `authenticated` de
 * proposito (e um token de sessao, nao dado de agencia) - por isso usa o
 * client service_role aqui dentro, depois de confirmar que quem chamou e
 * colaborador ativo (exigirColaboradorPorToken, mesma auth do resto de
 * /api/extensao/*).
 */
export async function POST(req: Request) {
  const { erro } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const body = (await req.json().catch(() => null)) as {
    access_token?: string;
    refresh_token?: string;
    expira_em?: number;
  } | null;

  if (!body || typeof body.refresh_token !== "string" || !body.refresh_token) {
    return Response.json({ error: "refresh_token obrigatório" }, { status: 400 });
  }

  const admin = createSupabaseClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );

  const { error } = await admin.from("milhasflow_auth_state").upsert(
    {
      id: "lfviagens",
      access_token: body.access_token ?? null,
      refresh_token: body.refresh_token,
      expira_em: typeof body.expira_em === "number" ? body.expira_em : null,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "id" },
  );

  if (error) return Response.json({ error: error.message }, { status: 400 });
  return Response.json({ ok: true });
}
