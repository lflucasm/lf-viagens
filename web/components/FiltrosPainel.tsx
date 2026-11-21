import Form from "next/form";
import Link from "next/link";
import type { Perfil } from "@/lib/tipos";
import { BotaoEnviar } from "@/components/BotaoEnviar";

type Props = {
  cias: string[];
  atendentes: Perfil[];
  valores: {
    cia: string;
    status: string;
    resolvido: string;
    atendente: string;
    embarque: string;
    passageiro: string;
  };
};

export function FiltrosPainel({ cias, atendentes, valores }: Props) {
  return (
    // next/form: filtra por navegação no cliente (sem recarregar a página
    // inteira) e deixa o botão mostrar "Filtrando…" enquanto carrega.
    <Form action="/" className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white/90 p-3">
      <Campo label="Passageiro">
        <input
          type="search"
          name="passageiro"
          defaultValue={valores.passageiro}
          placeholder="Nome do passageiro"
          className={`${CAMPO} w-56`}
        />
      </Campo>

      <Campo label="Companhia">
        <select name="cia" defaultValue={valores.cia} className={CAMPO}>
          <option value="">Todas</option>
          {cias.map((cia) => (
            <option key={cia} value={cia}>
              {cia}
            </option>
          ))}
        </select>
      </Campo>

      <Campo label="Status">
        <select name="status" defaultValue={valores.status} className={CAMPO}>
          <option value="">Todos</option>
          <option value="alterado">Alterado</option>
          <option value="ok">Ok</option>
        </select>
      </Campo>

      <Campo label="Conferência">
        <select name="resolvido" defaultValue={valores.resolvido} className={CAMPO}>
          <option value="">Todos</option>
          <option value="pendente">Pendente</option>
          <option value="resolvido">Resolvido</option>
        </select>
      </Campo>

      <Campo label="Embarque">
        <select
          name="embarque"
          defaultValue={valores.embarque}
          className={CAMPO}
        >
          <option value="">A monitorar</option>
          <option value="todos">Todos</option>
          <option value="embarcados">Já embarcou</option>
        </select>
      </Campo>

      <Campo label="Atendente">
        <select
          name="atendente"
          defaultValue={valores.atendente}
          className={CAMPO}
        >
          <option value="">Todos</option>
          <option value="_nenhum">Sem atribuição</option>
          {atendentes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </select>
      </Campo>

      <BotaoEnviar variante="principal" pendente="Filtrando…">
        Filtrar
      </BotaoEnviar>
      <Link href="/" className="inline-flex h-9 items-center px-1 text-sm text-gray-500 hover:text-gray-900">
        Limpar
      </Link>
    </Form>
  );
}

const CAMPO = "h-9 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900";

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-gray-500">
      {label}
      {children}
    </label>
  );
}
