import Link from "next/link";
import { BotaoEnviar, Giro } from "@/components/BotaoEnviar";
import { aplicarNaVolly, ignorarProposta } from "@/app/(painel)/reserva/[id]/actions";
import { nomesPassageiros } from "@/lib/tipos";

type Status = "proposta" | "sem_proposta" | "nada_a_mudar" | "aplicada" | "descartada";

/**
 * Um rótulo e uma cor por status, no lugar do card inteiro pintado (azul,
 * âmbar, verde, esmeralda) que não dava pra distinguir. Dourado = espera
 * alguém decidir; verde = resolvido; âmbar = precisa de mão humana.
 */
const ESTADO: Record<Status, { rotulo: string; ponto: string; faixa: string; texto: string }> = {
  proposta: { rotulo: "Aguardando decisão", ponto: "bg-gold-500", faixa: "bg-gold-500", texto: "text-gray-900" },
  sem_proposta: { rotulo: "Ajustar à mão", ponto: "bg-atencao", faixa: "bg-atencao", texto: "text-atencao" },
  nada_a_mudar: { rotulo: "Volly já está certa", ponto: "bg-ok", faixa: "bg-ok/60", texto: "text-ok" },
  aplicada: { rotulo: "Aplicada na Volly", ponto: "bg-ok", faixa: "bg-ok", texto: "text-ok" },
  descartada: { rotulo: "Ignorada", ponto: "bg-gray-400", faixa: "bg-gray-300", texto: "text-gray-500" },
};

export type Troca = { campo: string; de: string; para: string };

/**
 * A mensagem gravada por src/proposta_volly.py é
 * "✏️ Na Volly mudaria — LOC NUM: partida 10/11 10:00 → 10/11 11:30; ...".
 * Vira uma linha por campo (o que a Volly tem hoje → o que a companhia diz).
 * Se o formato mudar, o texto cru continua aparecendo (trocas vazias).
 */
export function lerMensagemProposta(mensagem: string | null): { titulo: string; trocas: Troca[] } {
  const bruto = mensagem ?? "";
  const corpo = bruto.replace(/^✏️\s*Na Volly mudaria\s*—\s*/, "");
  const doisPontos = corpo.indexOf(": ");
  if (corpo === bruto || doisPontos < 0) return { titulo: bruto, trocas: [] };
  const trocas: Troca[] = [];
  for (const parte of corpo.slice(doisPontos + 2).split("; ")) {
    const m = parte.match(/^(\S+)\s+(.+?)\s+→\s+(.+)$/);
    if (!m) return { titulo: corpo, trocas: [] };
    trocas.push({ campo: m[1], de: m[2], para: m[3] });
  }
  return { titulo: corpo.slice(0, doisPontos), trocas };
}

type Props = {
  proposta: {
    id: number;
    voo_id: string;
    status: string;
    mensagem: string | null;
  };
  passageiros: string | null | undefined;
  /** Pedido de aplicar já feito e o robô ainda não respondeu. */
  aplicando: boolean;
  /** Linha de contexto em cinza: data, fonte, quem aplicou/ignorou. */
  detalhe?: React.ReactNode;
  /** Aviso da última tentativa (erro ou simulação). */
  aviso?: React.ReactNode;
  /** Na lista da aba Urgente o título leva pra reserva. */
  linkReserva?: boolean;
};

export function PropostaVolly({ proposta, passageiros, aplicando, detalhe, aviso, linkReserva }: Props) {
  const status = (proposta.status in ESTADO ? proposta.status : "descartada") as Status;
  const estado = ESTADO[status];
  // Proposta, aplicada e ignorada guardam a mesma mensagem "Na Volly mudaria";
  // sem_proposta/nada_a_mudar são texto livre e lerMensagemProposta devolve cru.
  const lida = lerMensagemProposta(proposta.mensagem);
  const trocas = lida.trocas;
  // o rótulo do status já diz "Ajustar à mão"/"Volly já está certa": o ⚠️/✅
  // do começo da mensagem (feito pro Telegram) só repetiria
  const titulo = trocas.length > 0 ? lida.titulo : lida.titulo.replace(/^\p{Extended_Pictographic}\uFE0F?\s*/u, "");
  const ignorada = status === "descartada";
  const nomes = nomesPassageiros(passageiros);

  return (
    <article className="relative overflow-hidden rounded-lg border border-gray-200 bg-white/90 py-3 pl-5 pr-4 text-sm">
      <span className={`absolute inset-y-0 left-0 w-1 ${estado.faixa}`} aria-hidden="true" />

      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${estado.texto}`}>
          {aplicando ? <Giro /> : <span className={`h-2 w-2 rounded-full ${estado.ponto}`} aria-hidden="true" />}
          {aplicando ? "Aplicando na Volly…" : estado.rotulo}
        </span>
        {trocas.length > 0 &&
          (linkReserva ? (
            <Link href={`/reserva/${proposta.voo_id}`} className="font-mono text-xs font-semibold text-gray-700 hover:underline">
              {titulo}
            </Link>
          ) : (
            <span className="font-mono text-xs font-semibold text-gray-700">{titulo}</span>
          ))}
        {nomes && <span className="text-xs text-gray-500">{nomes}</span>}
      </header>

      {trocas.length > 0 ? (
        <dl className="mt-2.5 grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-1.5">
          {trocas.map((t) => (
            <div key={t.campo} className="contents">
              <dt className="text-[11px] font-medium uppercase tracking-wider text-gray-500">{t.campo}</dt>
              <dd className="flex flex-wrap items-baseline gap-x-2 font-mono text-[13px]">
                <span className="text-gray-400 line-through decoration-gray-400/70" title="Na Volly hoje">
                  {t.de}
                </span>
                <span className="text-gray-400" aria-label="passa a ser">
                  →
                </span>
                <span
                  className={`rounded px-1.5 font-semibold ${ignorada ? "bg-gray-100 text-gray-600" : "bg-gold-100 text-navy-950"}`}
                  title="O que a companhia mostra"
                >
                  {t.para}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      ) : linkReserva ? (
        <Link href={`/reserva/${proposta.voo_id}`} className="mt-1.5 block text-gray-800 hover:underline">
          {titulo}
        </Link>
      ) : (
        <p className="mt-1.5 text-gray-800">{titulo}</p>
      )}

      {(detalhe || aviso) && (
        <div className="mt-2 space-y-0.5 text-xs text-gray-500">
          {detalhe && <p>{detalhe}</p>}
          {aviso && <p className="text-atencao">{aviso}</p>}
        </div>
      )}

      {status === "proposta" && !aplicando && (
        <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3">
          <p className="text-xs text-gray-500">Nada muda na Volly até você aplicar.</p>
          <div className="flex items-center gap-2">
            <form action={ignorarProposta}>
              <input type="hidden" name="proposta_id" value={proposta.id} />
              <input type="hidden" name="voo_id" value={proposta.voo_id} />
              <BotaoEnviar variante="discreto" tamanho="sm" pendente="Ignorando…" title="Descarta a proposta sem gravar nada na Volly">
                Ignorar
              </BotaoEnviar>
            </form>
            <form action={aplicarNaVolly}>
              <input type="hidden" name="proposta_id" value={proposta.id} />
              <input type="hidden" name="voo_id" value={proposta.voo_id} />
              <BotaoEnviar variante="marca" tamanho="sm" pendente="Enviando…" title="Grava esta correção no trecho da Volly">
                Aplicar na Volly
              </BotaoEnviar>
            </form>
          </div>
        </footer>
      )}
      {aplicando && (
        <p className="mt-2 text-xs text-gray-500">Leva 1 a 2 minutos. Recarregue a página para ver o resultado.</p>
      )}
    </article>
  );
}
