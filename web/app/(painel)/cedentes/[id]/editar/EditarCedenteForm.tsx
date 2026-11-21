"use client";

import { useActionState, useState } from "react";
import { Campo, INPUT_CLASSE, Secao } from "@/components/CadastroSecao";
import {
  PIX_TIPOS,
  ROTULO_PIX,
  dataIsoParaBr,
  mascararDataBr,
  normalizarTelefone,
  type Cedente,
} from "@/lib/cedentes";
import { atualizarCedente, type EstadoEdicaoCedente } from "../../actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

const estadoInicial: EstadoEdicaoCedente = { erro: null };

export function EditarCedenteForm({ cedente }: { cedente: Cedente }) {
  const [estado, acao] = useActionState(atualizarCedente, estadoInicial);
  const [nascimento, setNascimento] = useState(
    cedente.data_nascimento ? dataIsoParaBr(cedente.data_nascimento) : "",
  );
  const [telefone, setTelefone] = useState(cedente.telefone ?? "");

  return (
    <form action={acao} className="space-y-6">
      <input type="hidden" name="cedente_id" value={cedente.id} />

      <Secao titulo="Dados do titular">
        <Campo label="Nome completo" className="sm:col-span-2">
          <input
            name="nome_completo"
            required
            defaultValue={cedente.nome_completo}
            className={INPUT_CLASSE}
          />
        </Campo>
        <Campo label="CPF">
          <input name="cpf" required defaultValue={cedente.cpf} inputMode="numeric" className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Data de nascimento">
          <input
            name="data_nascimento"
            required
            inputMode="numeric"
            placeholder="DD/MM/AAAA"
            value={nascimento}
            onChange={(e) => setNascimento(mascararDataBr(e.target.value))}
            className={INPUT_CLASSE}
          />
        </Campo>
        <Campo label="Telefone com DDD">
          <input
            name="telefone"
            required
            inputMode="tel"
            value={telefone}
            onChange={(e) => setTelefone(normalizarTelefone(e.target.value))}
            className={INPUT_CLASSE}
          />
        </Campo>
      </Secao>

      <Secao titulo="Onde recebe">
        <Campo label="Banco">
          <input name="banco" defaultValue={cedente.banco ?? ""} className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Tipo da chave PIX">
          <select name="pix_tipo" defaultValue={cedente.pix_tipo ?? ""} className={INPUT_CLASSE}>
            <option value="">—</option>
            {PIX_TIPOS.map((t) => (
              <option key={t} value={t}>
                {ROTULO_PIX[t]}
              </option>
            ))}
          </select>
        </Campo>
        <Campo label="Chave PIX" className="sm:col-span-2">
          <input name="chave_pix" defaultValue={cedente.chave_pix ?? ""} className={INPUT_CLASSE} />
        </Campo>
      </Secao>

      <Secao titulo="Pontos">
        <Campo label="LATAM Pass">
          <input
            name="pontos_latam"
            inputMode="numeric"
            defaultValue={cedente.pontos_latam}
            className={INPUT_CLASSE}
          />
        </Campo>
        <Campo label="Smiles">
          <input
            name="pontos_smiles"
            inputMode="numeric"
            defaultValue={cedente.pontos_smiles}
            className={INPUT_CLASSE}
          />
        </Campo>
        <Campo label="Livelo">
          <input
            name="pontos_livelo"
            inputMode="numeric"
            defaultValue={cedente.pontos_livelo}
            className={INPUT_CLASSE}
          />
        </Campo>
        <Campo label="Esfera">
          <input
            name="pontos_esfera"
            inputMode="numeric"
            defaultValue={cedente.pontos_esfera}
            className={INPUT_CLASSE}
          />
        </Campo>
      </Secao>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}

      <div className="flex items-center gap-3">
        <BotaoEnviar variante="marca" pendente="Salvando…">
          Salvar alterações
        </BotaoEnviar>
      </div>
    </form>
  );
}
