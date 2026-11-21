"use client";

import { useSyncExternalStore } from "react";

type Tema = "light" | "dark" | null;

const CHAVE = "lf-tema";
const ouvintes = new Set<() => void>();

function obterTema(): Tema {
  const v = window.localStorage.getItem(CHAVE);
  return v === "light" || v === "dark" ? v : null;
}

const ESCURO_SISTEMA = "(prefers-color-scheme: dark)";

/** Escuro agora: escolha salva ou, sem ela, o tema do sistema. */
function obterEscuro(): boolean {
  const tema = obterTema();
  return tema === "dark" || (tema === null && window.matchMedia(ESCURO_SISTEMA).matches);
}

// O servidor não sabe o tema do sistema. Ler matchMedia direto no render
// fazia o navegador hidratar com sol e o servidor mandar lua (React #418 em
// toda página com o sistema no escuro, 19/11/2026); assim a hidratação usa
// este valor e só depois troca.
function obterEscuroServidor(): boolean {
  return false;
}

function inscrever(ouvir: () => void) {
  ouvintes.add(ouvir);
  const sistema = window.matchMedia(ESCURO_SISTEMA);
  sistema.addEventListener("change", ouvir);
  return () => {
    ouvintes.delete(ouvir);
    sistema.removeEventListener("change", ouvir);
  };
}

function definirTema(tema: Tema) {
  const root = document.documentElement;
  if (tema) {
    root.setAttribute("data-theme", tema);
    window.localStorage.setItem(CHAVE, tema);
  } else {
    root.removeAttribute("data-theme");
    window.localStorage.removeItem(CHAVE);
  }
  ouvintes.forEach((ouvir) => ouvir());
}

/**
 * Claro/escuro. Sem escolha salva, segue o tema do sistema operacional (a
 * media query em globals.css já cuida disso sem JS nenhum) — o botão só
 * entra quando alguém quer forçar um lado. `useSyncExternalStore` lê o
 * localStorage (estado fora do React) sem o efeito clássico de "montei,
 * agora sim posso ler" — o script em layout.tsx já aplicou essa mesma
 * escolha antes da 1ª pintura, pra não piscar no tema errado ao recarregar.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const escuroAgora = useSyncExternalStore(inscrever, obterEscuro, obterEscuroServidor);

  return (
    <button
      type="button"
      onClick={() => definirTema(escuroAgora ? "light" : "dark")}
      aria-label={escuroAgora ? "Usar tema claro" : "Usar tema escuro"}
      title={escuroAgora ? "Usar tema claro" : "Usar tema escuro"}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-haze-400 transition-colors hover:bg-navy-700 hover:text-cream-50 ${className}`}
    >
      {escuroAgora ? <IconeSol /> : <IconeLua />}
    </button>
  );
}

function IconeSol() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function IconeLua() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M20.8 14.5A9 9 0 1 1 9.5 3.2a7 7 0 0 0 11.3 11.3Z" />
    </svg>
  );
}
