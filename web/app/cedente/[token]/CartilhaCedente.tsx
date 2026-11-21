import Image from "next/image";

/**
 * Cartilha do cedente: a versão em página do PDF "Cartilha do cedente" (a
 * mesma que está em /cartilha-do-cedente.pdf). Aparece inteira antes de o
 * titular criar as contas e pode ser relida a qualquer momento em
 * /cedente/[token]/cartilha. Só marcação — sem estado, serve nos dois lugares.
 *
 * Lista de parceiros: a Livelo muda a rede o tempo todo; a regra vale pra
 * qualquer parceiro novo (o texto da seção diz isso).
 */

type Parceiro = { nome: string; logo: string; w: number; h: number; regra: string };

const REDE_STIX: Parceiro[] = [
  { nome: "Stix", logo: "stix", w: 426, h: 93, regra: "Usar a carteira Stix integrada para pagar com pontos." },
  { nome: "Postos Shell (Shell Box)", logo: "shell", w: 237, h: 156, regra: "Abastecer pagando com pontos Livelo, pelo app ou no caixa." },
  { nome: "Droga Raia", logo: "raia", w: 591, h: 117, regra: "Resgatar pontos por CPF para pagar produtos de farmácia." },
  { nome: "Drogasil", logo: "drogasil", w: 591, h: 81, regra: "Pagar medicamentos e itens de farmácia com pontos, no caixa ou no app." },
  { nome: "Pão de Açúcar", logo: "paodeacucar", w: 288, h: 141, regra: "Autorizar resgates de pontos ao digitar o CPF no caixa." },
  { nome: "Extra", logo: "extra", w: 582, h: 156, regra: "Usar pontos Livelo/Stix nas compras de mercado." },
  { nome: "Sodimac", logo: "sodimac", w: 384, h: 156, regra: "Pagar material de construção, ferramentas e itens para casa com pontos." },
];

const OUTROS: Parceiro[] = [
  { nome: "CVC", logo: "cvc", w: 237, h: 126, regra: "Trocar pontos por pacotes, passagens ou viagens CVC." },
  { nome: "Decolar", logo: "decolar", w: 477, h: 102, regra: "Usar pontos para reservar hotéis ou passagens no app." },
  { nome: "Amazon.com.br", logo: "amazon", w: 531, h: 75, regra: "Vincular a conta Livelo para pagar compras no site ou app." },
  { nome: "Rappi", logo: "rappi", w: 339, h: 90, regra: "Autorizar débito de pontos em pedidos de comida ou delivery." },
  { nome: "Petlove", logo: "petlove", w: 588, h: 90, regra: "Comprar produtos pet ou rações com os pontos." },
  { nome: "Supermercados Carone", logo: "carone", w: 393, h: 150, regra: "Informar o CPF no caixa para abater compras." },
  { nome: "Quartetto Supermercados", logo: "quartetto", w: 516, h: 90, regra: "Pagar compras de mercado com pontos Livelo." },
  { nome: "Reserva", logo: "reserva", w: 555, h: 63, regra: "Comprar roupas, calçados e acessórios com pontos." },
  { nome: "Dotz", logo: "dotz", w: 297, h: 72, regra: "Usar pontos Livelo na Dotz para trocar por produtos ou serviços." },
  { nome: "Luxury Loyalty", logo: "luxury", w: 417, h: 117, regra: "Trocar pontos por experiências ou hospedagens de luxo." },
];

const SITUACOES = [
  { icone: "🛒", titulo: "No caixa", onde: "Farmácia, mercado, loja de departamento", fala: "“Quer usar seus pontos Stix pra ganhar desconto?”", quem: "Atendente", resposta: "“Não, obrigado. Vou pagar no cartão.”" },
  { icone: "🪪", titulo: "Ao informar o CPF", onde: "Balcão ou caixa, ao se identificar", fala: "“Achei seus pontos. Quer abater do total?”", quem: "Atendente", resposta: "“Não use pontos. Quero pagar normal.”" },
  { icone: "⛽", titulo: "No posto Shell", onde: "App Shell Box, depois de digitar o código da bomba", fala: "“Pague com pontos Stix ou Livelo”", quem: "Tela do app", resposta: "Escolha cartão ou Pix e ignore a oferta." },
  { icone: "📱", titulo: "No app da loja", onde: "Pedido por app ou carteira Stix", fala: "“Usar meus pontos” já marcado", quem: "Tela do app", resposta: "Desmarque antes de confirmar o pagamento." },
  { icone: "🖥️", titulo: "Maquininha ou autoatendimento", onde: "Totem, PDV, pinpad", fala: "“Deseja usar pontos nesta compra?”", quem: "Tela", resposta: "Toque em “Não” e siga com cartão ou Pix." },
  { icone: "🎁", titulo: "“Hoje tem desconto”", onde: "Promoção, insistência ou “é de graça”", fala: "“Com pontos fica R$ 20 mais barato!”", quem: "Atendente", resposta: "“Obrigado, mas pago em dinheiro.”" },
];

const OUTROS_PROGRAMAS = [
  { nome: "Esfera (Santander)", itens: ["Produtos de parceiros (Amazon, Época Cosméticos, Casas Bahia…)", "Vales-compra e gift cards (Uber, Cinemark, iFood…)", "Pontos + Dinheiro, com parcelamento do restante no cartão", "Esfera Viagens: passagens, pacotes, hospedagens e taxas de embarque"] },
  { nome: "LATAM Pass", itens: ["Shopping LATAM Pass (“Usar pontos” no produto)", "Pontos + dinheiro para completar passagens", "Resgate de passagens, upgrades e serviços fora da emissão da LF", "Cupons de desconto no Shopping em campanhas"] },
  { nome: "Smiles", itens: ["Shopping Smiles e Smiles & Money (milhas + cartão)", "Resgate com Pix: paga em lojas por QR Code, até 100 mil milhas por mês", "Parceiros: Casas Bahia, Magalu, Fast Shop, Netshoes, Época Cosméticos…", "Resgates de passagem por conta própria"] },
  { nome: "Azul Fidelidade", itens: ["Shopping Azul: cerca de 550 mil itens", "Pontos + dinheiro, com pagamento parcelado", "Meu Resgate Favorito (assinantes do Clube Azul)", "Passagens, upgrades, hotéis e serviços de parceiros"] },
];

const RESPONSABILIDADES = [
  { t: "Manter telefone e e-mail ativos", d: "O celular e o e-mail vinculados às contas devem continuar sob seu controle, para receber códigos de verificação (SMS/token)." },
  { t: "Atender às verificações faciais", d: "Quando a LF Viagens pedir validação por biometria facial, faça o procedimento com agilidade." },
  { t: "Não interferir na operação", d: "Não faça resgates, trocas de senha, alterações cadastrais ou compras por conta própria nas plataformas sob gestão da LF Viagens. Isso inclui aceitar “pontos Stix” no caixa." },
  { t: "Sigilo e confidencialidade", d: "Manter sigilo sobre os dados e as estratégias da parceria. Seus dados são protegidos conforme a LGPD." },
];

const ALERTAS = [
  "Pontos Stix", "PagStix", "Usar pontos", "Pagar com pontos", "Abater do total",
  "Desconto em pontos", "Resgatar", "Pix com pontos", "Pontos viram dinheiro", "Pontos + dinheiro",
];

function CartaoParceiro({ p }: { p: Parceiro }) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-gray-100 bg-white/90 p-3 shadow-sm">
      <div className="flex h-14 w-28 shrink-0 items-center justify-center rounded-md bg-[#fff] p-2">
        <Image
          src={`/parceiros/${p.logo}.png`}
          alt={p.nome}
          width={p.w}
          height={p.h}
          className="max-h-10 w-auto max-w-full object-contain"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-gray-900">{p.nome}</p>
        <p className="text-xs leading-snug text-gray-600">
          <strong className="text-red-700">Proibido</strong> {p.regra.charAt(0).toLowerCase() + p.regra.slice(1)}
        </p>
      </div>
      <span className="shrink-0 rounded bg-red-600 px-2 py-1 text-[10px] font-extrabold tracking-wide text-white">
        PROIBIDO
      </span>
    </li>
  );
}

function Titulo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <span className="inline-block rounded-full bg-red-600 px-3 py-1 text-[10px] font-bold tracking-wider text-white uppercase">
        {etiqueta}
      </span>
      <h2 className="text-xl font-bold leading-tight text-gray-900 sm:text-2xl">{children}</h2>
    </div>
  );
}

export function CartilhaCedente() {
  return (
    <div className="space-y-10">
      {/* Faixa que acompanha a leitura inteira */}
      <p className="sticky top-0 z-10 rounded-lg bg-red-600 px-4 py-2 text-center text-xs font-extrabold tracking-wide text-white shadow-md sm:text-sm">
        🚫 PROIBIDO FAZER QUALQUER RESGATE DE PONTOS
      </p>

      {/* Regra principal */}
      <div className="rounded-xl border-2 border-red-400 bg-red-50 p-6 text-center shadow-sm">
        <p className="text-4xl font-black leading-tight text-red-700 sm:text-5xl">
          É PROIBIDO fazer resgate de pontos.
        </p>
        <p className="mt-3 text-lg font-bold text-red-700 sm:text-xl">
          Nem pequeno, nem “só dessa vez”, nem com desconto.
        </p>
        <p className="mt-3 text-base font-semibold text-red-600 sm:text-lg">
          Os pontos da conta foram comprados com dinheiro da LF Viagens. Resgatar, pagar ou
          converter pontos é prejuízo financeiro direto.
        </p>
      </div>

      <div className="rounded-xl border-2 border-red-300 bg-red-600 p-5 text-center text-white shadow-sm">
        <p className="text-xl font-extrabold leading-snug sm:text-2xl">
          ⛔ O cedente que fizer esse tipo de resgate está sujeito ao{" "}
          <span className="underline decoration-2 underline-offset-4">
            encerramento definitivo da parceria
          </span>{" "}
          com a LF Viagens.
        </p>
      </div>

      {/* PagStix */}
      <section className="space-y-4">
        <Titulo etiqueta="Alerta de confusão frequente">
          PagStix: o desconto que sai da sua Livelo
        </Titulo>
        <p className="text-sm leading-relaxed text-gray-700">
          Nas lojas parceiras, o pagamento com pontos aparece como “pontos Stix”. Parece um
          desconto da própria loja — mas por trás está a sua conta Livelo.
        </p>

        <ol className="grid gap-2 sm:grid-cols-4">
          {[
            ["🏪", "A loja pergunta: “usar pontos Stix?”"],
            ["🔁", "Os pontos Livelo viram pontos Stix automaticamente"],
            ["📉", "O saldo sai da conta Livelo gerida pela LF"],
            ["💸", "Prejuízo: pontos comprados perdidos"],
          ].map(([ic, tx], i) => (
            <li
              key={i}
              className={`rounded-lg border p-3 text-center text-sm ${i === 0 ? "border-gray-200 bg-white/90 text-gray-800" : "border-red-300 bg-red-50 text-red-700"}`}
            >
              <div className="text-2xl">{ic}</div>
              {tx}
            </li>
          ))}
        </ol>

        <div className="rounded-xl border-2 border-gold-400 bg-gold-100/70 p-4">
          <p className="text-base font-bold leading-snug text-navy-900 sm:text-lg">
            Mesmo que o atendente pergunte só por “pontos Stix”, o valor sai da sua conta Livelo
            gerida pela LF Viagens. Não autorize sob nenhuma hipótese.
          </p>
        </div>

        <p className="text-sm font-semibold text-gray-900">Onde o PagStix existe (rede Stix):</p>
        <p className="flex flex-wrap gap-1.5">
          {["Shell (app Shell Box)", "Droga Raia", "Drogasil", "Pão de Açúcar", "Extra", "C&A", "Sodimac"].map((n) => (
            <span key={n} className="rounded-full border border-red-300 bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-700">
              {n}
            </span>
          ))}
        </p>
      </section>

      {/* Situações */}
      <section className="space-y-4">
        <Titulo etiqueta="Situações reais">Quando oferecem pontos no caixa</Titulo>
        <p className="text-sm leading-relaxed text-gray-700">
          Seis momentos em que a oferta costuma aparecer, vinda do atendente ou da tela. O texto
          exato muda de loja para loja. A resposta é sempre a mesma: <strong>não</strong>.
        </p>
        <ul className="grid gap-3 sm:grid-cols-2">
          {SITUACOES.map((s) => (
            <li key={s.titulo} className="space-y-2 rounded-xl border border-gray-100 bg-white/90 p-4 shadow-sm">
              <p className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                <span className="text-xl">{s.icone}</span> {s.titulo}
              </p>
              <p className="text-xs text-gray-500">{s.onde}</p>
              <p className="rounded-lg border border-pink-300 bg-pink-50 px-3 py-2 text-sm text-pink-900">
                <span className="block text-[10px] font-extrabold tracking-wider text-pink-700 uppercase">{s.quem}</span>
                {s.fala}
              </p>
              <p className="ml-6 rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-900">
                <span className="block text-[10px] font-extrabold tracking-wider text-green-700 uppercase">Você</span>
                {s.resposta}
              </p>
            </li>
          ))}
        </ul>
      </section>

      {/* Resposta pronta */}
      <section className="space-y-4">
        <Titulo etiqueta="Como agir">A resposta pronta</Titulo>
        <div className="rounded-2xl border-2 border-green-400 bg-green-50 p-6 text-center">
          <p className="text-[10px] font-extrabold tracking-[0.2em] text-green-700 uppercase">Diga isto</p>
          <p className="mt-1 text-2xl font-extrabold leading-tight text-green-900 sm:text-3xl">
            “Não, obrigado. Não quero usar pontos.”
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-green-300 bg-green-50 p-4">
            <p className="text-sm font-bold text-green-800">✅ Sempre</p>
            <ul className="mt-2 space-y-1.5 text-sm text-green-900">
              <li>Pague do seu bolso: cartão, dinheiro ou Pix.</li>
              <li>Diga “não” antes de informar o CPF.</li>
              <li>Confira a forma de pagamento antes de confirmar.</li>
              <li>Em caso de dúvida, recuse e pergunte à LF.</li>
              <li>Pode acumular pontos em compras: isso é bem-vindo.</li>
            </ul>
          </div>
          <div className="rounded-xl border border-red-300 bg-red-50 p-4">
            <p className="text-sm font-bold text-red-700">❌ Nunca</p>
            <ul className="mt-2 space-y-1.5 text-sm text-red-900">
              <li><strong>Fazer qualquer resgate de pontos, em qualquer lugar.</strong></li>
              <li>Autorizar “pontos Stix” no caixa, no app ou na máquina.</li>
              <li>Vincular a conta Livelo à carteira Stix.</li>
              <li>Abater fatura de cartão (Bradesco ou Banco do Brasil).</li>
              <li>Deixar alguém usar o app da conta “para aproveitar”.</li>
              <li>Fazer pelo seu CPF qualquer resgate, troca ou compra por conta própria.</li>
            </ul>
          </div>
        </div>

        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-bold">🚨 Aconteceu sem querer?</p>
          <ol className="mt-1 list-decimal space-y-1 pl-5">
            <li><strong>Avise a LF Viagens na hora</strong>, com print ou foto do comprovante.</li>
            <li>Pergunte ao atendente se a venda ainda pode ser cancelada.</li>
            <li>Não esconda: quanto mais cedo soubermos, mais fácil resolver.</li>
          </ol>
        </div>

        <div>
          <p className="mb-1.5 text-sm font-semibold text-gray-900">Palavras que acendem o alerta:</p>
          <p className="flex flex-wrap gap-1.5">
            {ALERTAS.map((a) => (
              <span key={a} className="rounded-md bg-navy-900 px-2.5 py-1 text-xs font-semibold text-cream-50">
                {a}
              </span>
            ))}
          </p>
        </div>
      </section>

      {/* Parceiros */}
      <section className="space-y-4">
        <Titulo etiqueta="Parceiros com resgate proibido">Rede Stix: lojas físicas e apps</Titulo>
        <p className="text-sm leading-relaxed text-gray-700">
          A Livelo é integrada a dezenas de lojas parceiras. Nestas, o pagamento com pontos
          aparece no caixa, no app ou na bomba.
        </p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {REDE_STIX.map((p) => <CartaoParceiro key={p.nome} p={p} />)}
        </ul>
        <p className="text-xs text-gray-500">A C&amp;A também integra o PagStix. A regra é a mesma.</p>

        <div className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-bold text-red-700">💳 Desconto em fatura bancária também é proibido</p>
          <p className="mt-1">
            Os apps do <strong>Bradesco</strong> e do <strong>Banco do Brasil</strong> oferecem
            usar pontos para abater a fatura. É proibido pedir cashback ou crédito na fatura do
            Bradesco e proibido pedir abatimento de fatura no Banco do Brasil.
          </p>
        </div>

        <h3 className="pt-2 text-lg font-bold text-gray-900">Outros parceiros da Livelo</h3>
        <p className="text-sm leading-relaxed text-gray-700">
          Online, delivery, viagens e supermercados: o pagamento com pontos também aparece aqui.
        </p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {OUTROS.map((p) => <CartaoParceiro key={p.nome} p={p} />)}
        </ul>
        <p className="text-xs text-gray-500">
          A lista muda: parceiros novos entram o tempo todo. Se um parceiro novo aceitar pontos,
          a regra é a mesma — proibido.
        </p>
      </section>

      {/* Outros programas */}
      <section className="space-y-4">
        <Titulo etiqueta="Os outros programas">Esfera, LATAM Pass, Smiles e Azul</Titulo>
        <p className="text-sm leading-relaxed text-gray-700">
          Mesma regra: todos têm algum jeito de “gastar” pontos. Nenhum deles pode ser usado.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {OUTROS_PROGRAMAS.map((p) => (
            <div key={p.nome} className="rounded-xl border border-red-200 bg-white/90 p-4 shadow-sm">
              <p className="text-sm font-bold text-gray-900">{p.nome}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-gray-700">
                {p.itens.map((i) => <li key={i}>{i}</li>)}
              </ul>
            </div>
          ))}
        </div>
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <strong>E as transferências entre programas?</strong> Mover pontos de um programa para
          outro (ex.: Livelo ➜ LATAM Pass) também gasta saldo. Só faça isso se a LF Viagens
          pedir. Acumular é permitido e bem-vindo: o problema é sempre o <em>gasto</em> de pontos.
        </div>
      </section>

      {/* Responsabilidades */}
      <section className="space-y-4">
        <Titulo etiqueta="Suas responsabilidades">Suas responsabilidades como cedente</Titulo>
        <ol className="space-y-2">
          {RESPONSABILIDADES.map((r, i) => (
            <li key={r.t} className="flex items-start gap-3 rounded-xl border border-gray-100 bg-white/90 p-4 shadow-sm">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-900 text-sm font-bold text-cream-50">
                {i + 1}
              </span>
              <span>
                <span className="block text-sm font-semibold text-gray-900">{r.t}</span>
                <span className="block text-sm leading-relaxed text-gray-600">{r.d}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-bold text-red-700">⚠ O que NÃO fazer durante a parceria</p>
          <p className="mt-1">
            Trocar senhas sem avisar, cancelar o número de telefone, não responder às validações
            ou bloquear o acesso da LF Viagens gera prejuízos financeiros graves, com compras de
            pontos em andamento e passagens já emitidas. O uso indevido de pontos é falta grave
            do termo que você aceitou. <strong>O cedente que fizer qualquer resgate está sujeito
            ao encerramento definitivo da parceria</strong>, além do bloqueio ou suspensão da
            conta e da responsabilização pelo prejuízo causado à LF Viagens.
          </p>
        </div>
      </section>
    </div>
  );
}

/**
 * Última etapa do cadastro: aparece na página das contas quando as contas
 * obrigatórias ficam prontas (ver page.tsx), depois do passo a passo.
 */
export function CartilhaFinal({ children }: { children?: React.ReactNode }) {
  return (
    <section id="cartilha" className="mt-12 scroll-mt-6 space-y-8 border-t-2 border-red-300 pt-8">
      <div className="space-y-2">
        <p className="text-xs font-bold tracking-wider text-red-700 uppercase">Última etapa</p>
        <h2 className="text-2xl font-bold leading-tight text-gray-900">
          Leia a cartilha do cedente
        </h2>
        <p className="text-sm leading-relaxed text-gray-700">
          Agora que o cadastro das contas terminou, leia com atenção o que você <strong>nunca</strong>{" "}
          pode fazer com os pontos — principalmente na Livelo — e o que responder quando um
          atendente oferecer desconto em pontos.{" "}
          <a
            href="/cartilha-do-cedente.pdf"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold text-gold-600 underline underline-offset-2 hover:text-gold-500"
          >
            Baixar em PDF
          </a>
        </p>
      </div>
      <CartilhaCedente />
      {children}
    </section>
  );
}
