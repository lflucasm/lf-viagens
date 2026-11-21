import { createClient } from "@/lib/supabase/server";
import type { ContaEmissao, Liberacao } from "@/lib/sugestaoConta";
import { SugestaoConta } from "./SugestaoConta";

export const dynamic = "force-dynamic";

const TRES_DIAS = 3 * 86_400_000;

export default async function PaginaEmissao() {
  const supabase = await createClient();
  const { data } = await supabase.from("contas_emissao").select("*").order("titular");
  const todas = data ?? [];

  // Conta que sumiu da Volly fica parada na tabela; 3 dias sem atualizar = não confiar no saldo.
  const agora = Date.now();
  const recentes = todas.filter((c) => agora - new Date(c.atualizado_em).getTime() < TRES_DIAS);
  const comSaldo: ContaEmissao[] = recentes
    .filter((c) => c.saldo > 0)
    .map((c) => ({
      id: c.conta_id,
      titular: c.titular,
      programa: c.programa,
      saldo: c.saldo,
      cpm: c.cpm != null ? Number(c.cpm) : null,
      clubeAtivo: c.clube_ativo,
      cpfUsados: c.cpf_usados,
      cpfLimite: c.cpf_limite,
      liberacoes: (c.liberacoes as Liberacao[]) ?? [],
    }));
  const atualizado = recentes.reduce((m, c) => (c.atualizado_em > m ? c.atualizado_em : m), "");
  const hoje = new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" }); // AAAA-MM-DD

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Sugestão de conta</h1>
        <p className="text-sm text-gray-500">
          Informe o programa, as milhas e os passageiros: as contas com saldo aparecem ordenadas pelo melhor
          encaixe, com os CPFs que sobram depois da emissão.
          {atualizado &&
            ` Saldos da Volly de ${new Date(atualizado).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}.`}
        </p>
      </div>
      <SugestaoConta contas={comSaldo} hoje={hoje} semSaldo={recentes.length - comSaldo.length} />
    </div>
  );
}
