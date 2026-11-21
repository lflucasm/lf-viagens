"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { exigirColaborador } from "@/lib/auth";

/**
 * "Liberar alertas segurados": grava supervisor_estado `telegram_liberado`
 * pela RPC (security definer, só colaborador ativo). Quem manda os alertas é
 * o próximo checador da nuvem que rodar (src/nuvem_comum.enviar_alertas) —
 * o site não fala com o Telegram.
 */
export async function liberarAlertasSegurados() {
  await exigirColaborador();

  const supabase = await createClient();
  const { error } = await supabase.rpc("liberar_alertas_segurados");
  if (error) throw new Error(error.message);

  revalidatePath("/urgente");
}
