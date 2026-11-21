import { carregarLinhasVoos } from "@/lib/painel";
import { ORDEM_PRIORIDADE } from "@/lib/prioridade";
import { FiltrosPainel } from "@/components/FiltrosPainel";
import { TabelaVoos } from "@/components/TabelaVoos";
import { passageiroCorresponde } from "@/lib/tipos";

type BuscaParams = { [chave: string]: string | string[] | undefined };

function pegarString(valor: string | string[] | undefined): string {
  if (Array.isArray(valor)) return valor[0] ?? "";
  return valor ?? "";
}

export default async function PaginaPrincipal({
  searchParams,
}: {
  searchParams: Promise<BuscaParams>;
}) {
  const sp = await searchParams;
  const filtroCia = pegarString(sp.cia);
  const filtroStatus = pegarString(sp.status);
  const filtroResolvido = pegarString(sp.resolvido);
  const filtroAtendente = pegarString(sp.atendente);
  const filtroEmbarque = pegarString(sp.embarque);
  const filtroPassageiro = pegarString(sp.passageiro).trim();

  const { linhas, cias, atendentes } = await carregarLinhasVoos();

  // Voo que já embarcou não tem mais o que monitorar: fica de fora por padrão.
  // "todos" traz de volta junto com os futuros; "embarcados" mostra só eles.
  const base =
    filtroEmbarque === "todos"
      ? linhas
      : filtroEmbarque === "embarcados"
        ? linhas.filter((l) => l.prioridade === "passado")
        : linhas.filter((l) => l.prioridade !== "passado");

  const filtradas = base.filter((l) => {
    if (filtroPassageiro && !passageiroCorresponde(l.voo.passageiros, filtroPassageiro)) return false;
    if (filtroCia && l.voo.cia !== filtroCia) return false;

    if (filtroStatus === "alterado" && l.pendente?.evento !== "alterado") return false;
    if (filtroStatus === "ok" && l.pendente) return false;

    if (filtroResolvido === "pendente" && !l.pendente) return false;
    if (filtroResolvido === "resolvido" && l.pendente) return false;

    if (filtroAtendente === "_nenhum" && (!l.pendente || l.pendente.atendente_id)) return false;
    if (
      filtroAtendente &&
      filtroAtendente !== "_nenhum" &&
      l.pendente?.atendente_id !== filtroAtendente
    )
      return false;

    return true;
  });

  filtradas.sort(
    (a, b) =>
      ORDEM_PRIORIDADE[a.prioridade] - ORDEM_PRIORIDADE[b.prioridade] ||
      (a.voo.embarque ?? "").localeCompare(b.voo.embarque ?? ""),
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Voos monitorados</h1>
        <p className="text-sm text-gray-500">
          {filtradas.length} de {base.length} reserva(s)
          {filtroEmbarque === "embarcados"
            ? " já embarcada(s)"
            : filtroEmbarque === "todos"
              ? " ativa(s)"
              : " a monitorar"}
        </p>
      </div>

      <FiltrosPainel
        cias={cias}
        atendentes={atendentes}
        valores={{
          cia: filtroCia,
          status: filtroStatus,
          resolvido: filtroResolvido,
          atendente: filtroAtendente,
          embarque: filtroEmbarque,
          passageiro: filtroPassageiro,
        }}
      />

      <TabelaVoos linhas={filtradas} />
    </div>
  );
}
