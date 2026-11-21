import "server-only";
import { createClient } from "@/lib/supabase/server";
import { linkPara, type LinkReserva } from "@/lib/linkReserva";
import { prioridade, type Prioridade } from "@/lib/prioridade";
import {
  ehAlerta,
  type Voo,
  type Historico,
  type Perfil,
  type SolicitacaoChecagem,
} from "@/lib/tipos";

export type LinhaVoo = {
  voo: Voo;
  pendente: Historico | null;
  ultimo: Historico | null;
  atendenteNome: string | null;
  link: LinkReserva;
  prioridade: Prioridade;
  checagemPendente: SolicitacaoChecagem | null;
  /** Até quando o alerta pendente foi adiado (só se ainda no futuro). */
  adiadoAte: string | null;
};

/**
 * Uma linha por voo ativo, com o alerta pendente (se houver) e o link pronto
 * pra abrir. Agrega em memória em vez de SQL porque o volume é pequeno
 * (~150 voos ativos) — ver README raiz, seção "escala".
 */
export async function carregarLinhasVoos(): Promise<{
  linhas: LinhaVoo[];
  cias: string[];
  atendentes: Perfil[];
}> {
  const supabase = await createClient();

  const [{ data: voos }, { data: historico }, { data: perfis }, { data: linksPdf },
         { data: solicitacoes }] =
    await Promise.all([
      supabase.from("voos").select("*").eq("ativo", true),
      supabase.from("historico").select("*").order("detectado_em", { ascending: false }),
      supabase.from("perfis").select("*").eq("ativo", true).order("nome"),
      supabase.from("links_pdf").select("localizador, url"),
      supabase.from("solicitacoes_checagem").select("*").eq("status", "pendente"),
    ]);

  const historicoPorVoo = new Map<string, Historico[]>();
  for (const h of historico ?? []) {
    const lista = historicoPorVoo.get(h.voo_id) ?? [];
    lista.push(h);
    historicoPorVoo.set(h.voo_id, lista);
  }

  const perfilPorId = new Map((perfis ?? []).map((p) => [p.id, p.nome]));
  const checagemPorVoo = new Map((solicitacoes ?? []).map((s) => [s.voo_id, s]));
  const doPdf = new Map(
    (linksPdf ?? [])
      .filter((l): l is { localizador: string; url: string } => Boolean(l.url))
      .map((l) => [l.localizador.toUpperCase(), l.url]),
  );

  const agora = new Date();
  const linhas: LinhaVoo[] = (voos ?? []).map((voo) => {
    const eventos = historicoPorVoo.get(voo.id) ?? [];
    const pendente = eventos.find((e) => !e.resolvido && ehAlerta(e)) ?? null;
    const ultimo = eventos[0] ?? null;
    return {
      voo,
      pendente,
      ultimo,
      atendenteNome: pendente?.atendente_id
        ? (perfilPorId.get(pendente.atendente_id) ?? null)
        : null,
      link: linkPara(voo, doPdf),
      prioridade: prioridade(voo.embarque),
      checagemPendente: checagemPorVoo.get(voo.id) ?? null,
      adiadoAte:
        pendente?.adiado_ate && new Date(pendente.adiado_ate) > agora ? pendente.adiado_ate : null,
    };
  });

  const cias = [
    ...new Set((voos ?? []).map((v) => v.cia).filter((c): c is string => Boolean(c))),
  ].sort();

  return { linhas, cias, atendentes: perfis ?? [] };
}
