import Link from "next/link";
import { notFound } from "next/navigation";
import { exigirAdmin } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { EditarCedenteForm } from "./EditarCedenteForm";
import { EditarContasCedente } from "./EditarContasCedente";

export const dynamic = "force-dynamic";

export default async function PaginaEditarCedente({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await exigirAdmin();
  const supabase = await createClient();

  const { data: cedente } = await supabase.from("cedentes").select("*").eq("id", id).maybeSingle();
  if (!cedente) notFound();

  // cedente_credenciais não tem policy de select pra authenticated de
  // propósito (só service_role lê) — mesmo motivo de revelarCredenciais()
  // em (painel)/cedentes/actions.ts.
  const admin = createAdminClient();
  const [{ data: contas }, { data: credenciais }] = await Promise.all([
    supabase
      .from("cedente_contas")
      .select("programa, status, login, observacao")
      .eq("cedente_id", id)
      .order("ordem"),
    admin
      .from("cedente_credenciais")
      .select("programa")
      .eq("cedente_id", id)
      .eq("campo", "senha"),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/cedentes/${id}`} className="text-sm text-gray-500 hover:text-gray-900">
          ← {cedente.nome_completo}
        </Link>
        <h1 className="mt-1 text-xl font-semibold">Editar cadastro</h1>
      </div>

      <EditarCedenteForm cedente={cedente} />

      <EditarContasCedente
        cedenteId={id}
        contas={contas ?? []}
        comSenha={(credenciais ?? []).map((c) => c.programa)}
      />
    </div>
  );
}
