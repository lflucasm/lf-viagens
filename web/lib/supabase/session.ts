import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const ROTA_LOGIN = "/login";

/**
 * Renova a sessão a cada request e redireciona pra /login quando não há
 * usuário autenticado. Precisa ser aqui (não só nas páginas) porque é o
 * único lugar do fluxo onde um cookie renovado pode ser persistido de
 * volta no navegador — Server Component não escreve cookie (limitação do
 * Next.js), então se o refresh só acontecer lá, o cookie novo é descartado
 * a cada request e a sessão nunca fica estável (loop de login observado ao
 * tirar essa checagem do proxy).
 *
 * A checagem se repete em cada Server Component/Action (ver lib/auth.ts) —
 * defesa em profundidade, porque um matcher mal ajustado pode deixar uma
 * rota passar sem passar pelo proxy.
 */
export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const naPaginaDeLogin = request.nextUrl.pathname.startsWith(ROTA_LOGIN);

  if (!user && !naPaginaDeLogin) {
    const url = request.nextUrl.clone();
    url.pathname = ROTA_LOGIN;
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
