import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/session";

export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  matcher: [
    // api/extensao/* fica de fora: são chamadas da extensão Chrome,
    // autenticadas por Bearer token (ver app/api/extensao/_auth.ts), não
    // por cookie de sessão — redirecionar pra /login quebraria o fetch.
    //
    // convite/* e cedente/* também: são as duas telas públicas da área de
    // cedentes. Quem abre não tem (nem vai ter) conta no painel — o que
    // autoriza ali é o código do convite e o token do cadastro, validados
    // dentro da própria rota com service_role.
    "/((?!_next/static|_next/image|favicon.ico|api/extensao|convite|cedente|.*\\.(?:svg|png|jpg|jpeg|gif|webp|pdf)$).*)",
  ],
};
