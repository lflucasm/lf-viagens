import { exigirAdmin } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { NovoColaboradorForm } from "./NovoColaboradorForm";
import { alternarAtivo } from "./actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

export default async function PaginaUsuarios() {
  await exigirAdmin();

  const supabase = await createClient();
  const { data: perfis } = await supabase.from("perfis").select("*").order("nome");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Usuários</h1>
        <p className="text-sm text-gray-500">Colaboradores com acesso ao painel.</p>
      </div>

      <NovoColaboradorForm />

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">Nome</th>
              <th className="px-3 py-2">Papel</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(perfis ?? []).map((p) => (
              <tr key={p.id} className="border-b border-gray-100 last:border-0">
                <td className="px-3 py-2">{p.nome}</td>
                <td className="px-3 py-2">{p.papel}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${p.ativo ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
                  >
                    {p.ativo ? "ativo" : "desativado"}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <form action={alternarAtivo}>
                    <input type="hidden" name="perfil_id" value={p.id} />
                    <input type="hidden" name="ativo" value={(!p.ativo).toString()} />
                    <BotaoEnviar tamanho="sm" pendente={p.ativo ? "Desativando…" : "Reativando…"}>
                      {p.ativo ? "Desativar" : "Reativar"}
                    </BotaoEnviar>
                  </form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
