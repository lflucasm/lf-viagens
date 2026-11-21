import { exigirColaboradorPorToken } from "../_auth";
import { limparPrograma } from "../_precos";

/**
 * PUT /api/extensao/precos-config
 * body: { overrides?: { [programa]: number | null }, markup?: { tipo, valor, escopo } }
 *
 * A aba "Preços" do popup salva aqui. `milheiro_manual = null` (ou <= 0) apaga
 * o override e o programa volta a usar a média de mercado. Escrita passa pela
 * RLS de colaborador (mesmo client JWT do _auth).
 */
export async function PUT(req: Request) {
  const { erro, perfil, supabase } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const body = (await req.json().catch(() => null)) as {
    overrides?: Record<string, number | null>;
    markup?: { tipo?: string; valor?: number; escopo?: string };
  } | null;
  if (!body || typeof body !== "object") {
    return Response.json({ error: "corpo inválido" }, { status: 400 });
  }

  const agora = new Date().toISOString();

  if (body.overrides && typeof body.overrides === "object") {
    const linhas = Object.entries(body.overrides).map(([programa, v]) => ({
      programa: limparPrograma(programa),
      milheiro_manual: v == null || Number(v) <= 0 ? null : Number(v),
      atualizado_em: agora,
      atualizado_por: perfil.id,
    }));
    if (linhas.length) {
      const { error } = await supabase
        .from("config_precos_extensao")
        .upsert(linhas, { onConflict: "programa" });
      if (error) return Response.json({ error: error.message }, { status: 400 });
    }
  }

  if (body.markup && typeof body.markup === "object") {
    const { error } = await supabase
      .from("config_markup_extensao")
      .update({
        tipo: body.markup.tipo === "abs" ? "abs" : "pct",
        valor: Math.max(0, Number(body.markup.valor) || 0),
        escopo: body.markup.escopo === "pessoa" ? "pessoa" : "venda",
        atualizado_em: agora,
        atualizado_por: perfil.id,
      })
      .eq("id", true);
    if (error) return Response.json({ error: error.message }, { status: 400 });
  }

  return Response.json({ ok: true });
}
