import Link from "next/link";
import { exigirColaborador } from "@/lib/auth";
import { LogoLF } from "@/components/LogoLF";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LinkNav } from "@/components/LinkNav";
import { sair } from "./actions";

export default async function LayoutPainel({ children }: { children: React.ReactNode }) {
  const { perfil } = await exigirColaborador();

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-navy-700 bg-marca">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
          <Link href="/" className="flex shrink-0 items-center gap-2 text-cream-50">
            <LogoLF size={22} />
            <span className="text-sm font-semibold tracking-wide">LF Viagens</span>
          </Link>
          <span className="hidden h-4 w-px bg-navy-600 md:block" aria-hidden="true" />
          {/* No celular a navegação vira uma 2ª linha que rola de lado, em vez de quebrar em 4 linhas. */}
          <nav className="order-last -mx-4 flex w-[calc(100%+2rem)] items-center gap-5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:order-none md:mx-0 md:w-auto md:flex-1 md:px-0">
            <LinkNav href="/">
              Voos
            </LinkNav>
            <LinkNav href="/urgente">
              Urgente
            </LinkNav>
            <LinkNav href="/pendencias">
              Pendências
            </LinkNav>
            <LinkNav href="/cedentes">
              Cedentes
            </LinkNav>
            <LinkNav href="/clubes">
              Clubes
            </LinkNav>
            <LinkNav href="/turbo">
              Turbo
            </LinkNav>
            <LinkNav href="/emissao">
              Emissão
            </LinkNav>
            <LinkNav href="/saude">
              Saúde
            </LinkNav>
            {perfil.papel === "admin" && (
              <>
                <LinkNav href="/cedentes/termos">
                  Termos
                </LinkNav>
                <LinkNav href="/usuarios">
                  Usuários
                </LinkNav>
              </>
            )}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-3 text-sm text-haze-400 md:ml-0">
            <span>
              {perfil.nome}
              <span
                className={`ml-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                  perfil.papel === "admin"
                    ? "bg-gold-500/15 text-gold-400"
                    : "bg-navy-700 text-haze-400"
                }`}
              >
                {perfil.papel}
              </span>
            </span>
            <form action={sair}>
              <button type="submit" className="text-haze-500 hover:text-cream-50">
                Sair
              </button>
            </form>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
