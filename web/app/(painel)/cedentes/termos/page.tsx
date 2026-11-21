import { exigirAdmin } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { alternarTermo } from "./actions";
import { NovoTermoForm } from "./NovoTermoForm";
import { BotaoEnviar } from "@/components/BotaoEnviar";

export const dynamic = "force-dynamic";

export default async function PaginaTermos() {
  await exigirAdmin();

  const supabase = await createClient();
  const { data: termos } = await supabase
    .from("termos_indicacao")
    .select("*")
    .order("criado_em", { ascending: false });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Termos do cadastro</h1>
        <p className="text-sm text-gray-500">
          O que o titular lê e aceita em <span className="font-mono">/convite</span>. Cada
          versão fica congelada — para mudar o texto, publique uma versão nova.
        </p>
      </div>

      <NovoTermoForm />

      <div className="space-y-3">
        {(termos ?? []).length === 0 && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            Nenhum termo publicado — enquanto isso, o link de convite não aceita cadastro.
          </p>
        )}
        {(termos ?? []).map((t) => (
          <details key={t.id} className="rounded-lg border border-gray-200 bg-white/90 p-4">
            <summary className="flex cursor-pointer flex-wrap items-center gap-3 text-sm">
              <span className="font-medium">{t.titulo}</span>
              <span className="font-mono text-xs text-gray-500">{t.versao}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${t.ativo ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
              >
                {t.ativo ? "no ar" : "arquivado"}
              </span>
            </summary>
            <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
              {t.corpo}
            </pre>
            <form action={alternarTermo} className="mt-3">
              <input type="hidden" name="termo_id" value={t.id} />
              <input type="hidden" name="ativo" value={(!t.ativo).toString()} />
              <BotaoEnviar tamanho="sm" pendente="Salvando…">
                {t.ativo ? "Arquivar" : "Colocar no ar"}
              </BotaoEnviar>
            </form>
          </details>
        ))}
      </div>
    </div>
  );
}
