import { createAdminClient } from "@/lib/supabase/admin";
import { LogoLF } from "@/components/LogoLF";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ConviteForm } from "./ConviteForm";

export const dynamic = "force-dynamic";

/**
 * Página pública de convite. Roda com service_role de propósito: quem abre
 * este link não tem conta no painel, então não existe sessão pra RLS avaliar
 * — o que autoriza a leitura é o código na URL, conferido aqui. Nada além do
 * nome do responsável e do texto do termo sai daqui pro navegador.
 */
export default async function PaginaConvite({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const admin = createAdminClient();

  const { data: convite } = await admin
    .from("convites")
    .select("id, codigo, ativo, colaborador_id")
    .ilike("codigo", code)
    .maybeSingle();

  // Duas queries em vez de um embed: database.types.ts é gerado com
  // Relationships vazio, e o client tipado rejeita o join.
  const { data: colaborador } = convite
    ? await admin.from("perfis").select("nome, ativo").eq("id", convite.colaborador_id).maybeSingle()
    : { data: null };

  if (!convite || !convite.ativo || !colaborador?.ativo) {
    return (
      <main className="flex flex-1 items-center justify-center bg-marca p-6">
        <div className="w-full max-w-md space-y-3 rounded-xl border border-navy-700 bg-navy-800 p-6 text-center shadow-sm">
          <LogoLF size={32} className="mx-auto" />
          <h1 className="text-base font-semibold text-cream-50">Convite inválido</h1>
          <p className="text-sm text-haze-400">
            Este link não está mais ativo. Peça um novo para quem te indicou.
          </p>
        </div>
      </main>
    );
  }

  const { count: termosAtivos } = await admin
    .from("termos_indicacao")
    .select("id", { count: "exact", head: true })
    .eq("ativo", true);

  if (!termosAtivos) {
    return (
      <main className="flex flex-1 items-center justify-center bg-marca p-6">
        <div className="w-full max-w-md space-y-3 rounded-xl border border-navy-700 bg-navy-800 p-6 text-center shadow-sm">
          <LogoLF size={32} className="mx-auto" />
          <h1 className="text-base font-semibold text-cream-50">Cadastro indisponível</h1>
          <p className="text-sm text-haze-400">
            O termo de cadastro ainda não foi publicado. Avise quem te enviou este link.
          </p>
        </div>
      </main>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="relative overflow-hidden border-b border-navy-700 bg-marca px-4 py-10 text-cream-50">
        <ThemeToggle className="absolute right-4 top-4" />
        <div className="relative mx-auto flex w-full max-w-2xl items-start gap-3">
          <LogoLF size={34} className="mt-1 shrink-0" />
          <div>
            <p className="text-xs font-medium tracking-[0.2em] text-gold-400 uppercase">
              LF Viagens
            </p>
            <h1 className="text-2xl text-cream-50">Cadastro de titular</h1>
            <p className="mt-2 max-w-md text-sm leading-relaxed text-haze-400">
              Você foi indicado por <strong className="text-cream-100">{colaborador.nome}</strong>.
              Preencha seus dados abaixo — depois a gente te acompanha, passo a passo, na
              criação das contas dos programas.
            </p>
          </div>
        </div>
      </div>

      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
        <ConviteForm codigo={convite.codigo} />
      </main>
    </div>
  );
}
