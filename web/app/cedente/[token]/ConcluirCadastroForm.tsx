"use client";

import { useActionState, useState } from "react";
import { Campo, INPUT_CLASSE, Secao } from "@/components/CadastroSecao";
import { PIX_TIPOS, ROTULO_PIX } from "@/lib/cedentes";
import { concluirCadastro, type EstadoRascunho } from "./actions";

type Termo = { id: string; titulo: string; versao: string; corpo: string };

const estadoInicial: EstadoRascunho = { erro: null };

export function ConcluirCadastroForm({ token, termos }: { token: string; termos: Termo[] }) {
  const [estado, acao, pendente] = useActionState(concluirCadastro, estadoInicial);
  const [termoId, setTermoId] = useState(termos[0]?.id ?? "");

  const termo = termos.find((t) => t.id === termoId) ?? null;

  if (termos.length === 0) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        O termo de cadastro ainda não foi publicado. Avise quem te enviou este link.
      </div>
    );
  }

  return (
    <form action={acao} className="space-y-6">
      <input type="hidden" name="token" value={token} />
      <input type="hidden" name="termo_versao" value={termo?.versao ?? ""} />

      <Secao titulo="Onde você recebe" descricao="O pagamento sai sempre para uma conta no seu próprio CPF.">
        <Campo label="Banco">
          <input name="banco" required className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Tipo da chave PIX">
          <select name="pix_tipo" required defaultValue="" className={INPUT_CLASSE}>
            <option value="" disabled>
              Escolha…
            </option>
            {PIX_TIPOS.map((t) => (
              <option key={t} value={t}>
                {ROTULO_PIX[t]}
              </option>
            ))}
          </select>
        </Campo>
        <Campo label="Chave PIX" className="sm:col-span-2">
          <input name="chave_pix" required className={INPUT_CLASSE} />
        </Campo>
      </Secao>

      <Secao
        titulo="Pontos que você já tem"
        descricao="Se ainda não tem conta em algum programa, deixe zero — a gente cria junto com você no próximo passo."
      >
        <Campo label="LATAM Pass">
          <input name="pontos_latam" inputMode="numeric" defaultValue={0} className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Smiles">
          <input name="pontos_smiles" inputMode="numeric" defaultValue={0} className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Livelo">
          <input name="pontos_livelo" inputMode="numeric" defaultValue={0} className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Esfera">
          <input name="pontos_esfera" inputMode="numeric" defaultValue={0} className={INPUT_CLASSE} />
        </Campo>
      </Secao>

      <section className="space-y-3 rounded-xl border border-gray-100 bg-white/90 p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-gray-900">Termo</h2>
          {termos.length > 1 && (
            <select
              value={termoId}
              onChange={(e) => setTermoId(e.target.value)}
              className="rounded-md border border-gray-300 px-2 py-1 text-sm"
            >
              {termos.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.titulo}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="rounded-lg border-2 border-red-300 bg-red-50 px-4 py-3 text-center">
          <p className="text-lg font-extrabold leading-snug text-red-700 sm:text-xl">
            Atenção para a leitura do termo a seguir
          </p>
        </div>

        <div className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md border border-gray-100 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
          {termo?.corpo}
        </div>

        <label className="flex items-start gap-2 text-sm text-gray-700">
          <input type="checkbox" name="aceite" required className="mt-0.5 accent-gold-500" />
          <span>
            Li e aceito o termo acima (versão {termo?.versao}). A data, o horário e o
            endereço de onde estou aceitando ficam registrados.
          </span>
        </label>
      </section>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}

      <button
        type="submit"
        disabled={pendente}
        className="w-full rounded-md bg-gold-500 px-4 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-600 disabled:opacity-50 sm:w-auto"
      >
        {pendente ? "Enviando…" : "Continuar"}
      </button>
    </form>
  );
}
