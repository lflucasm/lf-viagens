import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { LogoLF } from "@/components/LogoLF";
import { LoginForm } from "./LoginForm";

export default async function PaginaLogin() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="flex flex-1 items-center justify-center bg-marca p-6">
      {user ? (
        <div className="w-full max-w-sm space-y-4 rounded-xl border border-navy-700 bg-navy-800 p-6 text-center shadow-sm">
          <LogoLF size={32} className="mx-auto" />
          <p className="text-sm text-haze-400">Você já está logado.</p>
          <Link
            href="/"
            className="inline-block rounded-md bg-gold-500 px-3 py-2 text-sm font-semibold text-navy-950 hover:bg-gold-600"
          >
            Ir para o painel
          </Link>
        </div>
      ) : (
        <LoginForm />
      )}
    </main>
  );
}
