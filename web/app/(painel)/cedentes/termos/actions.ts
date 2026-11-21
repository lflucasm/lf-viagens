"use server";

import { revalidatePath } from "next/cache";
import { createAdminClient } from "@/lib/supabase/admin";
import { exigirAdmin } from "@/lib/auth";

export type EstadoTermo = { erro: string | null; sucesso: string | null };

function slugificar(titulo: string) {
  const s = titulo
    .normalize("NFD")
    .replace(/\p{Diacritic}+/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return s || "termo";
}

/**
 * Publica uma versão nova do termo. Versão é única e nunca é reescrita: o
 * aceite guarda a versão, então editar o texto de uma versão já assinada
 * mudaria, retroativamente, o que alguém concordou.
 */
export async function publicarTermo(
  _estado: EstadoTermo,
  formData: FormData,
): Promise<EstadoTermo> {
  await exigirAdmin();

  const titulo = String(formData.get("titulo") ?? "").trim();
  const versao = String(formData.get("versao") ?? "").trim();
  const corpo = String(formData.get("corpo") ?? "").trim();

  if (!titulo || !versao || corpo.length < 50) {
    return { erro: "Preencha título, versão e o texto completo do termo.", sucesso: null };
  }

  const admin = createAdminClient();

  let slug = slugificar(titulo);
  for (let n = 1; ; n += 1) {
    const { data } = await admin.from("termos_indicacao").select("id").eq("slug", slug).maybeSingle();
    if (!data) break;
    slug = `${slugificar(titulo)}-${n}`;
  }

  const { error } = await admin
    .from("termos_indicacao")
    .insert({ titulo, versao, corpo, slug, ativo: true });

  if (error) {
    return {
      erro: error.message.includes("termos_indicacao_versao_key")
        ? "Já existe um termo com essa versão. Use outro número."
        : error.message,
      sucesso: null,
    };
  }

  revalidatePath("/cedentes/termos");
  return { erro: null, sucesso: `Termo ${versao} publicado.` };
}

export async function alternarTermo(formData: FormData) {
  await exigirAdmin();

  const id = String(formData.get("termo_id"));
  const ativo = formData.get("ativo") === "true";

  const admin = createAdminClient();
  const { error } = await admin
    .from("termos_indicacao")
    .update({ ativo, atualizado_em: new Date().toISOString() })
    .eq("id", id);
  if (error) throw new Error(error.message);

  revalidatePath("/cedentes/termos");
}
