import { createAdminClient } from "@/lib/supabase/admin";
import { CARTILHA_VERSAO, PROGRAMAS } from "@/lib/cedentes";
import { LogoLF } from "@/components/LogoLF";
import { ThemeToggle } from "@/components/ThemeToggle";
import { PassoAPasso } from "./PassoAPasso";
import { CartilhaCedente, CartilhaFinal } from "./CartilhaCedente";
import { ConfirmarCartilha } from "./ConfirmarCartilha";
import { ConcluirCadastroForm } from "./ConcluirCadastroForm";
import { AvisoContas } from "./AvisoContas";

export const dynamic = "force-dynamic";

/**
 * Cadastro guiado das contas. O token na URL faz as vezes de senha — é o
 * que o titular usa pra voltar e continuar de onde parou, sem criar login.
 */
export default async function PaginaCedente({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("id, nome_completo, identificador, status, ativo, aviso_contas_confirmado_em")
    .eq("token_acesso", token)
    .maybeSingle();

  if (!cedente || !cedente.ativo) {
    return (
      <main className="flex flex-1 items-center justify-center bg-marca p-6">
        <div className="w-full max-w-md space-y-3 rounded-xl border border-navy-700 bg-navy-800 p-6 text-center shadow-sm">
          <LogoLF size={32} className="mx-auto" />
          <h1 className="text-base font-semibold text-cream-50">
            {cedente ? "Cadastro desativado" : "Link não encontrado"}
          </h1>
          <p className="text-sm text-haze-400">
            {cedente
              ? "Este cadastro não está mais ativo. Fale com quem te indicou."
              : "Confira se você copiou o endereço inteiro, ou peça um novo para quem te indicou."}
          </p>
        </div>
      </main>
    );
  }

  if (cedente.status === "rascunho") {
    const { data: termos } = await admin
      .from("termos_indicacao")
      .select("id, titulo, versao, corpo")
      .eq("ativo", true)
      .order("ordem");

    const primeiroNome = cedente.nome_completo.split(/\s+/)[0];

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
              <h1 className="text-2xl text-cream-50">Falta pouco, {primeiroNome}</h1>
              <p className="mt-2 max-w-md text-sm leading-relaxed text-haze-400">
                Confirme onde receber o pagamento e aceite o termo. Guarde este link — é ele
                que te traz de volta se precisar sair no meio do caminho.
              </p>
            </div>
          </div>
        </div>

        <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
          <ConcluirCadastroForm token={token} termos={termos ?? []} />
        </main>
      </div>
    );
  }

  if (!cedente.aviso_contas_confirmado_em) {
    const primeiroNome = cedente.nome_completo.split(/\s+/)[0];

    return (
      <div className="flex flex-1 flex-col">
        <div className="relative border-b border-navy-700 bg-marca px-4 py-8 text-cream-50">
          <ThemeToggle className="absolute right-4 top-4" />
          <div className="mx-auto flex w-full max-w-2xl items-center gap-3">
            <LogoLF size={34} className="shrink-0" />
            <div>
              <p className="text-xs font-medium tracking-[0.2em] text-gold-400 uppercase">
                LF Viagens
              </p>
              <h1 className="text-2xl text-cream-50">Antes de começar, {primeiroNome}</h1>
            </div>
          </div>
        </div>

        <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
          <AvisoContas token={token} />
        </main>
      </div>
    );
  }

  const { data: contas } = await admin
    .from("cedente_contas")
    .select("id, programa, status, login, observacao, concluida_em")
    .eq("cedente_id", cedente.id)
    .order("ordem");

  // Só quais programas já têm senha guardada — o valor cifrado não sai do
  // servidor nem para o próprio titular.
  const { data: credenciais } = await admin
    .from("cedente_credenciais")
    .select("programa")
    .eq("cedente_id", cedente.id)
    .eq("campo", "senha");

  // Ciência da cartilha (aceites_termo, versão atual) — prova de que o titular leu.
  const { data: ciencia } = await admin
    .from("aceites_termo")
    .select("aceito_em")
    .eq("cedente_id", cedente.id)
    .eq("termo_versao", CARTILHA_VERSAO)
    .order("aceito_em")
    .limit(1)
    .maybeSingle();
  const cartilhaLidaEm = ciencia?.aceito_em ?? null;

  // Esfera fica de fora da contagem obrigatória de propósito — só as
  // outras 4 travam a conclusão (ver PassoAPasso.tsx pro roteiro dela).
  const obrigatorios = PROGRAMAS.filter((p) => p.chave !== "esfera");
  const concluidasObrigatorias = (contas ?? []).filter(
    (c) => c.status === "concluida" && c.programa !== "esfera",
  ).length;
  const tudoPronto = concluidasObrigatorias === obrigatorios.length;
  const primeiroNome = cedente.nome_completo.split(/\s+/)[0];

  // A Esfera fecha de dois jeitos: conta criada, ou o cedente avisou que não
  // conseguiu (status "nao_criada"). Com as 4 obrigatórias + a Esfera resolvida,
  // o cadastro acabou e a única coisa que resta é a cartilha: ela ocupa a
  // página inteira e só sai quando a leitura for confirmada.
  const statusEsfera = (contas ?? []).find((c) => c.programa === "esfera")?.status;
  const esferaResolvida = statusEsfera === "concluida" || statusEsfera === "nao_criada";

  if (tudoPronto && esferaResolvida && !cartilhaLidaEm) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="relative border-b border-navy-700 bg-marca px-4 py-8 text-cream-50">
          <ThemeToggle className="absolute right-4 top-4" />
          <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
            <LogoLF size={34} className="shrink-0" />
            <div>
              <p className="text-xs font-medium tracking-[0.2em] text-gold-400 uppercase">
                LF Viagens
              </p>
              <h1 className="text-2xl text-cream-50">Última etapa, {primeiroNome}</h1>
            </div>
          </div>
        </div>

        <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
          <CartilhaFinal>
            <ConfirmarCartilha token={token} />
          </CartilhaFinal>
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="relative border-b border-navy-700 bg-marca px-4 py-8 text-cream-50">
        <ThemeToggle className="absolute right-4 top-4" />
        <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
          <LogoLF size={34} className="shrink-0" />
          <div>
            <p className="text-xs font-medium tracking-[0.2em] text-gold-400 uppercase">
              LF Viagens
            </p>
            <h1 className="text-2xl text-cream-50">Vamos criar suas contas, {primeiroNome}</h1>
          </div>
        </div>
      </div>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <p className="mb-6 text-sm leading-relaxed text-gray-600">
          São {PROGRAMAS.length} contas, uma parada por vez. Faça no seu ritmo, na ordem que
          quiser — o progresso fica salvo e este mesmo link te traz de volta.{" "}
          <strong className="text-gray-900">
            {concluidasObrigatorias} de {obrigatorios.length} contas prontas.
          </strong>
        </p>

        {tudoPronto && !esferaResolvida && (
          <div className="mb-6 rounded-xl border border-gold-400/60 bg-gold-100/70 p-4 text-sm text-navy-900">
            <strong>As 4 contas principais estão prontas.</strong> Falta a Esfera: crie a conta ou,
            se não conseguir, use o botão &ldquo;Não consegui criar essa conta Esfera&rdquo; no
            final do passo da Esfera. Depois disso você segue para a cartilha.
          </div>
        )}

        {tudoPronto && esferaResolvida && (
          <div className="mb-6 rounded-xl border border-gold-400/60 bg-gold-100/70 p-4 text-sm text-navy-900">
            <strong>Tudo pronto!</strong>{" "}
            {statusEsfera === "nao_criada"
              ? "As 4 contas principais foram criadas (a Esfera ficou de fora). "
              : "Todas as contas foram criadas. "}
            Pode deixar que a equipe da LF Viagens confere e dá continuidade — não precisa fazer
            mais nada por aqui.
          </div>
        )}

        <PassoAPasso
          token={token}
          contas={contas ?? []}
          comSenha={(credenciais ?? []).map((c) => c.programa)}
        />

        {tudoPronto && cartilhaLidaEm && (
          <details className="mt-10 rounded-xl border border-gray-100 bg-white/90 p-4 shadow-sm">
            <summary className="cursor-pointer text-sm font-semibold text-gray-900">
              Cartilha do cedente · lida em {new Date(cartilhaLidaEm).toLocaleDateString("pt-BR")}{" "}
              <span className="font-normal text-gray-500">(toque para reler)</span>
            </summary>
            <div className="mt-6">
              <CartilhaCedente />
            </div>
          </details>
        )}
      </main>
    </div>
  );
}
