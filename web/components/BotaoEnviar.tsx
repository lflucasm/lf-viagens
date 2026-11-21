"use client";

import { useFormStatus } from "react-dom";
import { classesBotao, type Tamanho, type Variante } from "@/components/botao";

type Props = {
  children: React.ReactNode;
  /** O que aparece enquanto a ação roda: "Aplicando…", "Salvando…". */
  pendente?: string;
  variante?: Variante;
  tamanho?: Tamanho;
  className?: string;
  title?: string;
  disabled?: boolean;
};

/**
 * Botão de submit de formulário com server action. Assim que é clicado, mostra
 * o giro e o texto de "fazendo" e trava novo clique até a resposta voltar.
 * Sem isso o botão ficava parado até o servidor responder e a equipe clicava
 * de novo achando que não tinha pegado.
 */
export function BotaoEnviar({
  children,
  pendente,
  variante = "contorno",
  tamanho = "md",
  className = "",
  title,
  disabled,
}: Props) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      title={title}
      disabled={disabled || pending}
      aria-busy={pending}
      className={classesBotao(variante, tamanho, className)}
    >
      {pending && <Giro />}
      {pending && pendente ? pendente : children}
    </button>
  );
}

export function Giro() {
  return (
    <svg
      className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
