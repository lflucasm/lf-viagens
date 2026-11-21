import type { LinkReserva } from "@/lib/linkReserva";
import { classesBotao } from "@/components/botao";

export function BotaoAbrirLink({ link }: { link: LinkReserva }) {
  if (!link.url) {
    return <span className="inline-flex h-7 items-center px-2.5 text-xs text-gray-400">sem link</span>;
  }

  return (
    <a
      href={link.url}
      target="_blank"
      rel="noopener noreferrer"
      className={classesBotao("principal", "sm")}
      title={link.origemLink}
    >
      Abrir
      <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" aria-hidden="true">
        <path d="M6 3h7v7M13 3L5 11" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </a>
  );
}
