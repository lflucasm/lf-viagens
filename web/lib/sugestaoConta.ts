// Sugestão de conta pra emissão. Ordem pelo encaixe de pontos (quem fica com menos
// sobra vem primeiro, pra não deixar milhas soltas), como na tela de venda do
// Trademiles; CPF estourado não elimina a conta, só desce na lista e avisa.

export type Liberacao = { data: string; qtd: number };

export type ContaEmissao = {
  id: string;
  titular: string;
  programa: string;
  saldo: number;
  cpm: number | null;
  clubeAtivo: boolean;
  cpfUsados: number;
  cpfLimite: number;
  liberacoes: Liberacao[];
};

export type Prioridade = "otima" | "boa" | "media" | "baixa" | "sem_saldo";

export type Sugestao = ContaEmissao & {
  sobra: number;
  cpfsDepois: number; // CPFs livres depois dessa emissão (negativo = estoura o limite)
  estoura: boolean;
  proximaLiberacao: Liberacao | null;
  prioridade: Prioridade;
};

// Faixas de sobra do Trademiles: até 2.000 zera a conta (ótima); acima de 10.000 ainda
// rende outra venda (boa); 3.000 a 10.000 é resto difícil de reaproveitar (baixa).
export function prioridadeDaSobra(sobra: number): Prioridade {
  if (sobra < 0) return "sem_saldo";
  if (sobra <= 2000) return "otima";
  if (sobra > 10000) return "boa";
  if (sobra >= 3000) return "baixa";
  return "media";
}

const PESO: Record<Prioridade, number> = { otima: 0, boa: 1, media: 2, baixa: 3, sem_saldo: 99 };

export function sugerirContas(
  contas: ContaEmissao[],
  entrada: { programa: string; milhas: number; cpfs: number },
  hoje: string,
): Sugestao[] {
  return contas
    .filter((c) => c.programa === entrada.programa)
    .map((c) => {
      const sobra = c.saldo - entrada.milhas;
      const cpfsDepois = c.cpfLimite - c.cpfUsados - entrada.cpfs;
      return {
        ...c,
        sobra,
        cpfsDepois,
        estoura: cpfsDepois < 0,
        proximaLiberacao: c.liberacoes.find((l) => l.data > hoje) ?? null,
        prioridade: prioridadeDaSobra(sobra),
      };
    })
    .sort(
      (a, b) =>
        PESO[a.prioridade] === 99 || PESO[b.prioridade] === 99
          ? PESO[a.prioridade] - PESO[b.prioridade] || b.saldo - a.saldo
          : Number(a.estoura) - Number(b.estoura) || PESO[a.prioridade] - PESO[b.prioridade] || a.sobra - b.sobra,
    );
}
