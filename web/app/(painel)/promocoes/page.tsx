import { createClient } from "@/lib/supabase/server";
import { EstadoVazio } from "@/components/EstadoVazio";

export const dynamic = "force-dynamic";

const TIPO: Record<string, string> = {
  compra_pontos: "Compra de pontos",
  transferencia_bonificada: "Transferência bonificada",
  clube: "Clube",
  resgate: "Resgate",
  outro: "Outro",
};

type Cenario = {
  plano: string;
  bonus_pct: number | null;
  custo_parcelado: number | null;
  custo_pix: number | null;
};

const ate = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

const reais = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}/k`;

// O resumo é o HTML do Telegram (<b>, entidades): no site vai como texto puro.
const textoPuro = (html: string) =>
  html
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&");

export default async function PaginaPromocoes() {
  const supabase = await createClient();
  const { data } = await supabase
    .from("promocoes")
    .select("*")
    .or(`fim.is.null,fim.gt.${new Date().toISOString()}`)
    .order("fim", { ascending: true, nullsFirst: false });
  const promocoes = data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Promoções ativas</h1>
        <p className="text-sm text-gray-500">
          Lidas dos grupos de milhas. O custo por milheiro final (com o bônus) é calculado pelo
          sistema; confira sempre o regulamento. Somem sozinhas quando acabam.
        </p>
      </div>

      {promocoes.length === 0 ? (
        <EstadoVazio titulo="Nenhuma promoção ativa">As promoções postadas nos grupos de milhas aparecem aqui com o custo por milheiro já calculado, e somem sozinhas quando acabam.</EstadoVazio>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {promocoes.map((p) => {
            const cenarios = (p.cenarios as Cenario[]) ?? [];
            return (
              <article
                key={p.id}
                className="space-y-2 rounded-lg border border-gray-200 bg-white/90 p-4"
              >
                <header className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="font-semibold">{p.programa}</h2>
                    <p className="text-xs text-gray-500">{TIPO[p.tipo] ?? p.tipo}</p>
                  </div>
                  {p.oportunidade && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                      🔥 abaixo do teto
                    </span>
                  )}
                </header>
                <p className="text-sm">
                  {p.fim ? `Até ${ate(p.fim)} (Brasília)` : "Sem data de fim informada"}
                </p>
                {cenarios.length > 0 && (
                  <ul className="space-y-1 text-sm">
                    {cenarios.map((c) => (
                      <li key={c.plano}>
                        <span className="font-medium">{c.plano}</span>:{" "}
                        {[c.custo_parcelado && `${reais(c.custo_parcelado)} parcelado`,
                          c.custo_pix && `${reais(c.custo_pix)} Pix`]
                          .filter(Boolean)
                          .join(" · ")}
                        {c.bonus_pct ? ` (com ${c.bonus_pct}% de bônus)` : ""}
                      </li>
                    ))}
                  </ul>
                )}
                <details className="text-xs text-gray-600">
                  <summary className="cursor-pointer">Resumo completo</summary>
                  <p className="mt-1 whitespace-pre-line">{textoPuro(p.resumo)}</p>
                </details>
                <footer className="text-xs text-gray-500">
                  Fonte: {p.fonte}
                  {p.mensagem_url && (
                    <>
                      {" · "}
                      <a href={p.mensagem_url} className="underline" target="_blank" rel="noreferrer">
                        mensagem
                      </a>
                    </>
                  )}
                </footer>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
