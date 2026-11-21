"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Link do cabeçalho; a aba aberta fica marcada com o fio dourado. */
export function LinkNav({ href, children }: { href: string; children: React.ReactNode }) {
  const caminho = usePathname();
  const ativo =
    href === "/"
      ? caminho === "/" || caminho.startsWith("/reserva")
      : caminho.startsWith(href) && !(href === "/cedentes" && caminho.startsWith("/cedentes/termos"));
  return (
    <Link
      href={href}
      aria-current={ativo ? "page" : undefined}
      className={`relative shrink-0 whitespace-nowrap py-1 text-sm transition-colors after:absolute after:inset-x-0 after:-bottom-0.5 after:h-0.5 after:rounded-full after:transition-colors ${
        ativo
          ? "text-cream-50 after:bg-gold-500"
          : "text-haze-400 after:bg-transparent hover:text-cream-50"
      }`}
    >
      {children}
    </Link>
  );
}
