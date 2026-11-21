import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { exigirColaborador } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import {
  PREFIXO_CARTILHA,
  PROGRAMAS,
  ROTULO_PIX,
  ROTULO_PROGRAMA,
  ROTULO_STATUS,
  formatarCpf,
  type PixTipo,
  type Programa,
} from "@/lib/cedentes";
import {
  aprovarCedente,
  rejeitarCedente,
  reabrirAnaliseCedente,
  reenviarParaCrm,
  inativarCedente,
  reativarCedente,
} from "../actions";
import { Credenciais } from "./Credenciais";
import { LinkRetomada } from "./LinkRetomada";
import { BotaoEnviar } from "@/components/BotaoEnviar";
import { classesBotao } from "@/components/botao";

export const dynamic = "force-dynamic";

const ROTULO_ETAPA: Record<string, string> = {
  pendente: "não começou",
  concluida: "criada",
  nao_criada: "cedente não conseguiu criar",
};

export default async function PaginaCedente({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { perfil } = await exigirColaborador();
  const supabase = await createClient();

  const { data: cedente } = await supabase.from("cedentes").select("*").eq("id", id).maybeSingle();
  if (!cedente) notFound();

  const [{ data: contas }, { data: aceites }, { data: perfis }] = await Promise.all([
    supabase
      .from("cedente_contas")
      .select("programa, status, login, observacao, milhasflow_id, milhasflow_enviado_em, milhasflow_erro")
      .eq("cedente_id", id)
      .order("ordem"),
    supabase
      .from("aceites_termo")
      .select("termo_versao, ip, aceito_em")
      .eq("cedente_id", id)
      .order("aceito_em", { ascending: false }),
    supabase.from("perfis").select("id, nome"),
  ]);

  const nomePorId = new Map((perfis ?? []).map((p) => [p.id, p.nome]));
  // aceites_termo guarda o termo e também a ciência da cartilha (versão "cartilha-…").
  const aceite = (aceites ?? []).find((a) => !a.termo_versao.startsWith(PREFIXO_CARTILHA)) ?? null;
  const cartilha = (aceites ?? []).find((a) => a.termo_versao.startsWith(PREFIXO_CARTILHA)) ?? null;
  const ehAdmin = perfil.papel === "admin";

  // Esfera fica de fora da contagem obrigatória de propósito, mesmo critério
  // usado em /cedente/[token]/page.tsx pra decidir se ainda falta o titular
  // criar alguma conta.
  const obrigatorios = PROGRAMAS.filter((p) => p.chave !== "esfera");
  const concluidasObrigatorias = (contas ?? []).filter(
    (c) => c.status === "concluida" && c.programa !== "esfera",
  ).length;
  const faltaCompletarContas = concluidasObrigatorias < obrigatorios.length;
  const precisaDoLink = cedente.status === "rascunho" || (cedente.status === "pendente" && faltaCompletarContas);

  const cabecalhos = await headers();
  const origem = `${cabecalhos.get("x-forwarded-proto") ?? "https"}://${cabecalhos.get("host")}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/cedentes" className="text-sm text-gray-500 hover:text-gray-900">
            ← Cedentes
          </Link>
          <h1 className="mt-1 text-xl font-semibold">{cedente.nome_completo}</h1>
          <p className="text-sm text-gray-500">
            <span className="font-mono">{cedente.identificador}</span> · indicado por{" "}
            {nomePorId.get(cedente.colaborador_id) ?? "—"} ·{" "}
            {ROTULO_STATUS[cedente.status] ?? cedente.status}
            {!cedente.ativo && <span className="ml-1 text-red-600">· inativo</span>}
          </p>
        </div>

        {ehAdmin && (
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/cedentes/${cedente.id}/editar`} className={classesBotao("contorno", "sm")}>
              Editar cadastro
            </Link>
            <form action={cedente.ativo ? inativarCedente : reativarCedente}>
              <input type="hidden" name="cedente_id" value={cedente.id} />
              <BotaoEnviar
                tamanho="sm"
                pendente={cedente.ativo ? "Excluindo…" : "Reativando…"}
                className={cedente.ativo ? "border-perigo/40 text-perigo hover:border-perigo hover:bg-perigo/10" : ""}
              >
                {cedente.ativo ? "Excluir cadastro" : "Reativar cadastro"}
              </BotaoEnviar>
            </form>
          </div>
        )}
      </div>

      {!cedente.ativo && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Este cadastro foi excluído (inativado). Os dados continuam guardados, mas o titular
          não consegue mais acessar o link de cadastro.
        </section>
      )}

      {ehAdmin && precisaDoLink && (
        <section className="space-y-2 rounded-xl border border-gold-400/60 bg-gold-100/50 p-4">
          <h2 className="text-sm font-semibold text-navy-900">
            Cadastro em andamento — falta o titular terminar
          </h2>
          <p className="text-sm text-navy-800">
            {cedente.status === "rascunho"
              ? "Reenvie este link se ele saiu no meio do preenchimento: é o mesmo link, e o progresso já feito continua salvo."
              : "Ele já preencheu os dados, mas ainda falta criar alguma conta de fidelidade. Reenvie este link pra ele continuar de onde parou."}
          </p>
          <LinkRetomada url={`${origem}/cedente/${cedente.token_acesso}`} />
        </section>
      )}

      {ehAdmin && cedente.status !== "rascunho" && (
        <section
          className={`flex flex-wrap items-center gap-3 rounded-xl border p-4 shadow-sm ${
            cedente.status === "pendente"
              ? "border-gold-400/60 bg-gold-100/50"
              : "border-gray-100 bg-white/90"
          }`}
        >
          {cedente.status === "pendente" ? (
            <>
              <p className="text-sm text-navy-800">
                Aprovar já envia o cadastro para o MilhasFlow.
              </p>
              <form action={aprovarCedente}>
                <input type="hidden" name="cedente_id" value={cedente.id} />
                <BotaoEnviar variante="marca" pendente="Enviando…">
                  Aprovar e enviar
                </BotaoEnviar>
              </form>
              <form action={rejeitarCedente}>
                <input type="hidden" name="cedente_id" value={cedente.id} />
                <BotaoEnviar pendente="Rejeitando…">Rejeitar</BotaoEnviar>
              </form>
            </>
          ) : (
            <>
              <p className="text-sm text-gray-600">
                {ROTULO_STATUS[cedente.status]} em{" "}
                {cedente.revisado_em
                  ? new Date(cedente.revisado_em).toLocaleString("pt-BR")
                  : "—"}{" "}
                por {nomePorId.get(cedente.revisado_por ?? "") ?? "—"}.
              </p>
              {cedente.status === "rejeitado" && (
                <form action={reabrirAnaliseCedente}>
                  <input type="hidden" name="cedente_id" value={cedente.id} />
                  <BotaoEnviar pendente="Reabrindo…">Trazer para análise novamente</BotaoEnviar>
                </form>
              )}
            </>
          )}
        </section>
      )}

      {cedente.status === "aprovado" && (
        <section className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">MilhasFlow</h2>
            {ehAdmin && (
              <form action={reenviarParaCrm}>
                <input type="hidden" name="cedente_id" value={cedente.id} />
                <BotaoEnviar tamanho="sm" pendente="Reenviando…">
                  Reenviar pendentes
                </BotaoEnviar>
              </form>
            )}
          </div>
          <p className="text-xs text-gray-500">
            Cada conta de programa vira uma linha própria lá — o e-mail não é enviado,
            só as contas de milhas criadas.
          </p>
          <ul className="space-y-1 text-sm">
            {PROGRAMAS.filter((p) => p.chave !== "email").map((p) => {
              const conta = (contas ?? []).find((c) => c.programa === p.chave);
              if (!conta || conta.status !== "concluida") {
                return (
                  <li key={p.chave} className="flex items-baseline gap-2 text-gray-400">
                    <span className="w-28 font-medium">{ROTULO_PROGRAMA[p.chave as Programa]}</span>
                    <span>
                      {conta?.status === "nao_criada"
                        ? "cedente não conseguiu criar"
                        : "conta ainda não criada"}
                    </span>
                  </li>
                );
              }
              return (
                <li key={p.chave} className="flex flex-wrap items-baseline gap-2">
                  <span className="w-28 font-medium">{ROTULO_PROGRAMA[p.chave as Programa]}</span>
                  {conta.milhasflow_enviado_em ? (
                    <span className="text-green-700">
                      enviado em {new Date(conta.milhasflow_enviado_em).toLocaleString("pt-BR")}
                      {conta.milhasflow_id && (
                        <span className="ml-1 font-mono text-xs text-gray-500">
                          ({conta.milhasflow_id})
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className="text-amber-700">
                      não enviado{conta.milhasflow_erro ? ` — ${conta.milhasflow_erro}` : ""}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section className="grid gap-4 rounded-lg border border-gray-200 bg-white/90 p-4 sm:grid-cols-2">
        <Dado rotulo="CPF" valor={formatarCpf(cedente.cpf)} />
        <Dado
          rotulo="Nascimento"
          valor={
            cedente.data_nascimento
              ? new Date(`${cedente.data_nascimento}T12:00:00`).toLocaleDateString("pt-BR")
              : "—"
          }
        />
        <Dado rotulo="Telefone" valor={cedente.telefone ?? "—"} />
        <Dado rotulo="E-mail criado" valor={cedente.email_criado ?? "—"} />
        <Dado rotulo="Banco" valor={cedente.banco ?? "—"} />
        <Dado
          rotulo="Chave PIX"
          valor={
            cedente.chave_pix
              ? `${cedente.chave_pix} (${ROTULO_PIX[cedente.pix_tipo as PixTipo] ?? cedente.pix_tipo})`
              : "—"
          }
        />
      </section>

      <section className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
        <h2 className="text-sm font-semibold">Contas</h2>
        <ul className="space-y-2 text-sm">
          {PROGRAMAS.map((p) => {
            const conta = (contas ?? []).find((c) => c.programa === p.chave);
            return (
              <li key={p.chave} className="flex flex-wrap items-baseline gap-2">
                <span className="w-28 font-medium">{ROTULO_PROGRAMA[p.chave as Programa]}</span>
                <span
                  className={
                    conta?.status === "concluida" ? "text-green-700" : "text-gray-500"
                  }
                >
                  {ROTULO_ETAPA[conta?.status ?? "pendente"]}
                </span>
                {conta?.login && <span className="text-gray-600">· {conta.login}</span>}
                {conta?.observacao && (
                  <span className="text-xs text-amber-700">· {conta.observacao}</span>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {ehAdmin && <Credenciais cedenteId={cedente.id} />}

      <section className="space-y-1 rounded-lg border border-gray-200 bg-white/90 p-4 text-sm">
        <h2 className="text-sm font-semibold">Aceite do termo</h2>
        {aceite ? (
          <p className="text-gray-600">
            Versão <span className="font-mono">{aceite.termo_versao}</span> em{" "}
            {new Date(aceite.aceito_em).toLocaleString("pt-BR")}
            {aceite.ip && <span className="text-gray-400"> · {aceite.ip}</span>}
          </p>
        ) : (
          <p className="text-gray-500">Sem registro de aceite.</p>
        )}
        <h2 className="pt-2 text-sm font-semibold">Ciência da cartilha (não resgatar pontos)</h2>
        {cartilha ? (
          <p className="text-gray-600">
            Versão <span className="font-mono">{cartilha.termo_versao}</span> em{" "}
            {new Date(cartilha.aceito_em).toLocaleString("pt-BR")}
            {cartilha.ip && <span className="text-gray-400"> · {cartilha.ip}</span>}
          </p>
        ) : (
          <p className="text-amber-700">Ainda não leu — cobre antes de operar a conta.</p>
        )}
      </section>
    </div>
  );
}

function Dado({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-500">{rotulo}</p>
      <p className="text-sm">{valor}</p>
    </div>
  );
}
