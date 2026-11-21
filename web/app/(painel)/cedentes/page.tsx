import Link from "next/link";
import { headers } from "next/headers";
import { exigirColaborador } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { ROTULO_STATUS, formatarCpf } from "@/lib/cedentes";
import { gerarMeuConvite, alternarConvite } from "./actions";
import { LinkConvite } from "./LinkConvite";
import { BotaoEnviar } from "@/components/BotaoEnviar";

export const dynamic = "force-dynamic";

export default async function PaginaCedentes() {
  const { perfil } = await exigirColaborador();
  const supabase = await createClient();

  const [{ data: convites }, { data: cedentes }, { data: perfis }] = await Promise.all([
    supabase.from("convites").select("*"),
    supabase
      .from("cedentes")
      .select("id, identificador, nome_completo, cpf, telefone, status, ativo, colaborador_id, criado_em")
      .order("criado_em", { ascending: false })
      .limit(200),
    supabase.from("perfis").select("id, nome"),
  ]);

  const meuConvite = (convites ?? []).find((c) => c.colaborador_id === perfil.id) ?? null;

  // A origem vem do request, não de window: o link é copiado e mandado pra
  // fora, então precisa do host público mesmo quando o painel roda atrás de
  // proxy — e montar no cliente causaria diferença entre servidor e primeira
  // renderização.
  const cabecalhos = await headers();
  const origem = `${cabecalhos.get("x-forwarded-proto") ?? "https"}://${cabecalhos.get("host")}`;
  const nomePorId = new Map((perfis ?? []).map((p) => [p.id, p.nome]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Cedentes</h1>
        <p className="text-sm text-gray-500">
          Titulares indicados pela equipe, pelo link de convite.
        </p>
      </div>

      <section className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
        <h2 className="text-sm font-semibold">Meu link de convite</h2>
        {meuConvite ? (
          <LinkConvite
            url={`${origem}/convite/${meuConvite.codigo}`}
            ativo={meuConvite.ativo}
            usos={meuConvite.usos}
          />
        ) : (
          <form action={gerarMeuConvite} className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-gray-600">Você ainda não tem um link.</p>
            <BotaoEnviar variante="principal" pendente="Gerando…">
              Gerar meu link
            </BotaoEnviar>
          </form>
        )}
      </section>

      {perfil.papel === "admin" && (convites ?? []).length > 0 && (
        <section className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
          <h2 className="text-sm font-semibold">Links da equipe</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-3 py-2">Colaborador</th>
                  <th className="px-3 py-2">Código</th>
                  <th className="px-3 py-2">Usos</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {(convites ?? []).map((c) => (
                  <tr key={c.id} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2">{nomePorId.get(c.colaborador_id) ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{c.codigo}</td>
                    <td className="px-3 py-2">{c.usos}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${c.ativo ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
                      >
                        {c.ativo ? "ativo" : "desativado"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <form action={alternarConvite}>
                        <input type="hidden" name="convite_id" value={c.id} />
                        <input type="hidden" name="ativo" value={(!c.ativo).toString()} />
                        <BotaoEnviar tamanho="sm" pendente={c.ativo ? "Desativando…" : "Reativando…"}>
                          {c.ativo ? "Desativar" : "Reativar"}
                        </BotaoEnviar>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">Titular</th>
              <th className="px-3 py-2">CPF</th>
              <th className="px-3 py-2">Telefone</th>
              <th className="px-3 py-2">Indicado por</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Cadastro</th>
            </tr>
          </thead>
          <tbody>
            {(cedentes ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-sm text-gray-500">
                  Nenhum cedente cadastrado ainda.
                </td>
              </tr>
            )}
            {(cedentes ?? []).map((c) => (
              <tr
                key={c.id}
                className={`border-b border-gray-100 last:border-0 ${!c.ativo ? "opacity-50" : ""}`}
              >
                <td className="px-3 py-2">
                  <Link href={`/cedentes/${c.id}`} className="font-medium hover:underline">
                    {c.nome_completo}
                  </Link>
                  <span className="ml-2 font-mono text-xs text-gray-400">{c.identificador}</span>
                </td>
                <td className="px-3 py-2">{formatarCpf(c.cpf)}</td>
                <td className="px-3 py-2">{c.telefone ?? "—"}</td>
                <td className="px-3 py-2">{nomePorId.get(c.colaborador_id) ?? "—"}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      c.status === "aprovado"
                        ? "bg-green-100 text-green-700"
                        : c.status === "rejeitado"
                          ? "bg-red-100 text-red-700"
                          : c.status === "rascunho"
                            ? "bg-gray-100 text-gray-600"
                            : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {ROTULO_STATUS[c.status] ?? c.status}
                  </span>
                  {!c.ativo && (
                    <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">
                      Inativo
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-gray-500">
                  {new Date(c.criado_em).toLocaleDateString("pt-BR")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
