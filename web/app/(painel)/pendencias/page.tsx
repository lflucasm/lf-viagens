import { createClient } from "@/lib/supabase/server";
import type { Pendencia } from "@/lib/tipos";
import { EstadoVazio } from "@/components/EstadoVazio";

export default async function PaginaPendencias() {
  const supabase = await createClient();
  const { data: pendencias } = await supabase
    .from("pendencias")
    .select("*")
    .order("cia")
    .order("localizador");

  const porCia = new Map<string, Pendencia[]>();
  for (const p of pendencias ?? []) {
    const lista = porCia.get(p.cia) ?? [];
    lista.push(p);
    porCia.set(p.cia, lista);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Pendências</h1>
        <p className="text-sm text-gray-500">
          Companhias sem checagem automática, ou que a checagem automática não
          conseguiu confirmar.
        </p>
      </div>

      {porCia.size === 0 ? (
        <EstadoVazio titulo="Nenhuma pendência">Quando uma companhia não tem checagem automática, ou a checagem não consegue confirmar a reserva, ela aparece aqui pra conferir à mão.</EstadoVazio>
      ) : (
        [...porCia.entries()].map(([cia, lista]) => (
          <section key={cia}>
            <h2 className="mb-2 text-sm font-semibold text-gray-700">
              {cia} ({lista.length})
            </h2>
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-3 py-2">Localizador</th>
                    <th className="px-3 py-2">Motivo</th>
                    <th className="px-3 py-2">Desde</th>
                  </tr>
                </thead>
                <tbody>
                  {lista.map((p) => (
                    <tr key={p.id} className="border-b border-gray-100 last:border-0">
                      <td className="px-3 py-2 font-mono">{p.localizador}</td>
                      <td className="px-3 py-2">{p.motivo}</td>
                      <td className="px-3 py-2 text-xs text-gray-500">{p.criado_em}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
