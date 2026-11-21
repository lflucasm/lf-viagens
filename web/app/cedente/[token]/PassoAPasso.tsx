"use client";

import { useActionState, useState } from "react";
import { PROGRAMAS, ROTULO_PROGRAMA, type Programa } from "@/lib/cedentes";
import { marcarContaNaoCriada, salvarConta, type EstadoAviso, type EstadoConta } from "./actions";

type Conta = {
  id: string;
  programa: string;
  status: string;
  login: string | null;
  observacao: string | null;
  concluida_em: string | null;
};

/**
 * Uma aba por conta. Texto vindo do PDF de instruções da agência
 * ("Criação de contas para cedentes LF Viagens", recebido em 20/08/2026).
 *
 * O roteiro da Esfera não veio do PDF (que não cobre esse programa) — foi
 * escrito olhando o cadastro em esfera.com.vc: pede CPF, dados pessoais,
 * confirmação por SMS e por e-mail (um código de 6 dígitos cada) e senha
 * numérica de 6 dígitos. Diferente da LATAM, o telefone não pode ser
 * reaproveitado em duas contas Esfera (dá erro no cadastro).
 *
 * O telefone (00) 00000-0000 e o e-mail hub@seudominio.com.br aparecem porque
 * o PDF pede pra cadastrar esse número como secundário nas contas (LATAM/
 * Smiles/Livelo), e — só pra quem já tinha conta ANTES, com o próprio
 * e-mail — configurar o encaminhamento das notificações da LATAM/Smiles pra
 * esse e-mail da agência. Esse encaminhamento em si (mexer na caixa de
 * entrada antiga) não está automatizado aqui: é feito à parte, com quem
 * indicou — a página com o passo a passo de encaminhamento ainda não existe.
 */
const ROTEIRO: Partial<Record<Programa, string[]>> = {
  email: [
    "Crie um e-mail novo no Gmail (gmail.com).",
    "Use o padrão NOME+SOBRENOME+LFV@gmail.com. Exemplo: para \"João Fernando Freitas Silva\", o e-mail fica joaosilvaLFV@gmail.com.",
    "Anote esse e-mail no campo abaixo — é ele que você vai usar para criar as contas dos outros programas.",
  ],
  latam: [
    "Acesse https://www.latamairlines.com/br/pt/cadastro.",
    "Se você AINDA NÃO tem conta na LATAM: cadastre-se usando o e-mail criado no passo anterior e o celular (00) 00000-0000.",
    "Se aparecer a tela \"Não foi possível criar sua conta\" pedindo pra ligar pra Central de Vendas: é comum acontecer com e-mail do Gmail recém-criado. Nesse caso, cadastre-se normalmente com o e-mail pessoal que você já usa no dia a dia (não o LFV) — mantendo o celular (00) 00000-0000. Depois, nossa equipe vai pedir direto pra LATAM a troca desse e-mail pelo LFV; a LATAM exige reconhecimento facial pra fazer essa troca.",
    "Se você JÁ TEM conta na LATAM: não é possível trocar o telefone cadastrado nela — não crie uma conta nova. Marque como \"criada\" com o login e a senha que você já usa. Se essa conta usa o SEU e-mail pessoal (não o LFV criado agora), avise quem te indicou: será preciso configurar o encaminhamento dos e-mails da LATAM para hub@seudominio.com.br.",
    "Guarde a senha no campo abaixo — recomendamos não usar uma senha que você usa em outro lugar.",
  ],
  smiles: [
    "Acesse https://www.smiles.com.br/cadastro.",
    "Se você AINDA NÃO tem conta na Smiles: cadastre-se usando o e-mail criado no passo anterior e o SEU celular.",
    "Se você JÁ TEM conta na Smiles: não precisa criar uma conta nova — marque como \"criada\" com o login e a senha que você já usa. Se essa conta usa o SEU e-mail pessoal (não o LFV criado agora), avise quem te indicou: será preciso configurar o encaminhamento dos e-mails da Smiles para hub@seudominio.com.br.",
    "Guarde a senha no campo abaixo — recomendamos não usar uma senha que você usa em outro lugar.",
  ],
  livelo: [
    "Acesse https://www.livelo.com.br/.",
    "Se você AINDA NÃO tem conta na Livelo: cadastre-se usando o e-mail criado no passo anterior e o SEU celular. Se pedir reconhecimento facial no cadastro, faça — só é exigido nessa hora. Depois de concluir, cadastre o celular (00) 00000-0000 como telefone secundário da conta.",
    "Se você JÁ TEM conta na Livelo: cadastre o celular (00) 00000-0000 como número secundário na conta e faça o reconhecimento facial pelo app, se ainda não tiver feito.",
    "Depois disso, entre na sua conta pelo aplicativo da Livelo no celular e faça o reconhecimento facial que será pedido no login.",
    "Guarde a senha no campo abaixo — recomendamos não usar uma senha que você usa em outro lugar.",
  ],
  esfera: [
    "Acesse https://www.esfera.com.vc/crie-sua-conta.",
    "Se você AINDA NÃO tem conta na Esfera: cadastre-se usando o e-mail criado no passo anterior e o celular (00) 00000-0000. Você vai receber um código de 6 dígitos por SMS e outro por e-mail — confirme os dois, depois crie a senha de acesso (6 números, sem repetir o mesmo dígito 3 vezes nem usar sequência). Se pedir reconhecimento facial em algum momento do cadastro, faça — só é exigido nessa hora. Se mesmo assim não conseguir concluir o cadastro com o celular (00) 00000-0000, use o SEU número de telefone — mas só nesse caso, depois de tentar com o nosso.",
    "Se você JÁ TEM conta na Esfera: não é possível trocar o telefone cadastrado nela — não crie uma conta nova (a Esfera nem deixa: dá erro se o número já estiver em uso). Marque como \"criada\" com o login e a senha que você já usa. Se essa conta usa o SEU e-mail pessoal (não o LFV criado agora), avise quem te indicou: será preciso configurar o encaminhamento dos e-mails da Esfera para hub@seudominio.com.br.",
    "Guarde a senha no campo abaixo — recomendamos não usar uma senha que você usa em outro lugar.",
  ],
};

const estadoInicial: EstadoConta = { erro: null, sucesso: null };
const estadoNaoInicial: EstadoAviso = { erro: null };

const RE_URL_SPLIT = /(https?:\/\/[^\s]*[^\s.,;:!?)])/g;
const RE_URL_TESTE = /^https?:\/\//;

/** Um passo do roteiro, com qualquer URL virando link clicável. */
function TextoDoPasso({ texto }: { texto: string }) {
  const partes = texto.split(RE_URL_SPLIT);
  return (
    <>
      {partes.map((parte, i) =>
        RE_URL_TESTE.test(parte) ? (
          <a
            key={i}
            href={parte}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gold-600 underline decoration-gold-300 underline-offset-2 hover:text-gold-500"
          >
            {parte}
          </a>
        ) : (
          <span key={i}>{parte}</span>
        ),
      )}
    </>
  );
}

/** Aviãozinho da rota — mesmo traço da marca (LogoLF), sozinho, indicando "você está aqui". */
function IconeAviao({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" className={className} aria-hidden="true">
      <path d="M2 21 22 12 2 3v7l13 2-13 2v7Z" />
    </svg>
  );
}

/**
 * A rota do cadastro: uma parada por conta de programa, na ordem em que se
 * cria. É uma sequência real (o próprio roteiro pede pra criar o e-mail
 * antes do resto), por isso a numeração/ordem aqui carrega informação de
 * verdade — não é enfeite.
 */
function RotaContas({
  contas,
  aberta,
  onEscolher,
}: {
  contas: Conta[];
  aberta: Programa;
  onEscolher: (p: Programa) => void;
}) {
  const indiceAberta = PROGRAMAS.findIndex((p) => p.chave === aberta);

  return (
    <ol className="grid w-full grid-flow-col auto-cols-fr">
      {PROGRAMAS.map((p, i) => {
        const c = contas.find((x) => x.programa === p.chave);
        const feita = c?.status === "concluida";
        const naoCriada = c?.status === "nao_criada";
        const ativa = p.chave === aberta;
        const linhaPercorrida = i < indiceAberta || feita || naoCriada;

        return (
          <li key={p.chave} className="relative flex flex-col items-center gap-2 px-1 pt-3.5">
            {i < PROGRAMAS.length - 1 && (
              <div
                aria-hidden
                className={`absolute left-1/2 top-[calc(0.875rem+13px)] h-0 w-full border-t-2 border-dotted ${
                  linhaPercorrida ? "border-gold-400" : "border-gray-200"
                }`}
              />
            )}
            <button
              type="button"
              onClick={() => onEscolher(p.chave)}
              aria-current={ativa ? "step" : undefined}
              className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors ${
                feita
                  ? "border-gold-500 bg-gold-500 text-navy-950"
                  : naoCriada && !ativa
                    ? "border-gold-500 bg-gray-50 text-gold-600"
                    : ativa
                    ? "border-navy-900 bg-navy-900 text-cream-50"
                    : "border-gray-300 bg-gray-50 text-gray-500 hover:border-gray-400"
              }`}
            >
              {feita ? "✓" : ativa ? <IconeAviao /> : naoCriada ? "–" : i + 1}
            </button>
            <span
              className={`text-center text-[11px] leading-tight ${
                ativa ? "font-semibold text-gray-900" : "text-gray-500"
              }`}
            >
              {p.rotulo}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function PassoAPasso({
  token,
  contas,
  comSenha,
}: {
  token: string;
  contas: Conta[];
  comSenha: string[];
}) {
  const [aberta, setAberta] = useState<Programa>(
    (contas.find((c) => c.status === "pendente")?.programa as Programa) ?? "email",
  );
  const [estado, acao, pendente] = useActionState(salvarConta, estadoInicial);
  const [estadoNao, acaoNao, pendenteNao] = useActionState(marcarContaNaoCriada, estadoNaoInicial);

  const conta = contas.find((c) => c.programa === aberta);
  const passos = ROTEIRO[aberta] ?? [];
  const senhaGuardada = comSenha.includes(aberta);

  return (
    <div className="space-y-6">
      <nav aria-label="Contas do cadastro" className="rounded-xl border border-gray-100 bg-white/90 px-4 py-4 shadow-sm">
        <RotaContas contas={contas} aberta={aberta} onEscolher={setAberta} />
      </nav>

      <form
        key={aberta}
        action={acao}
        className="space-y-5 rounded-xl border border-gray-100 bg-white/90 p-5 shadow-sm sm:p-6"
      >
        <input type="hidden" name="token" value={token} />
        <input type="hidden" name="programa" value={aberta} />

        <h2 className="text-xl font-medium text-gray-900">Conta {ROTULO_PROGRAMA[aberta]}</h2>

        {passos.length > 0 ? (
          <>
            <div className="rounded-lg border-2 border-red-300 bg-red-50 px-4 py-3 text-center">
              <p className="text-lg font-extrabold leading-snug text-red-700 sm:text-xl">
                Atenção: siga o passo a passo abaixo exatamente como está escrito. Se não
                seguir, não vai ser possível validar a conta e todo o processo será perdido.
              </p>
            </div>

            <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-gray-700">
              {passos.map((p, i) => (
                <li key={i}>
                  <TextoDoPasso texto={p} />
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="rounded-md border border-gold-400/60 bg-gold-100/60 p-3 text-sm text-navy-800">
            O passo a passo desta conta ainda não foi publicado. Siga junto com quem te
            indicou e registre aqui embaixo quando terminar.
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block space-y-1">
            <span className="block text-xs font-medium text-gray-600">
              {aberta === "email" ? "E-mail criado" : "Login (e-mail ou CPF)"}
            </span>
            <input
              name="login"
              required
              defaultValue={conta?.login ?? ""}
              autoComplete="off"
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-400/40"
            />
          </label>
          <label className="block space-y-1">
            <span className="block text-xs font-medium text-gray-600">
              Senha desta conta
              {senhaGuardada && (
                <span className="ml-1 font-normal text-gold-600">· já guardada</span>
              )}
            </span>
            <input
              name="senha"
              type="password"
              required={!senhaGuardada}
              autoComplete="new-password"
              placeholder={senhaGuardada ? "Deixe em branco para manter" : ""}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-400/40"
            />
          </label>
        </div>

        <label className="block space-y-1">
          <span className="block text-xs font-medium text-gray-600">
            Travou em alguma coisa? (opcional)
          </span>
          <textarea
            name="observacao"
            rows={2}
            defaultValue={conta?.observacao ?? ""}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-400/40"
          />
        </label>

        <p className="rounded-md bg-gray-50 p-3 text-xs leading-relaxed text-gray-600">
          A senha fica guardada em cofre cifrado e é usada só pela equipe da LF Viagens
          para operar a conta, como diz o termo que você aceitou. Nunca informe a senha do
          seu banco aqui — só a das contas dos programas de pontos.
        </p>

        {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}
        {estado.sucesso && <p className="text-sm text-green-700">{estado.sucesso}</p>}

        <button
          type="submit"
          disabled={pendente}
          className="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-600 disabled:opacity-50"
        >
          {pendente ? "Salvando…" : "Salvar e continuar"}
        </button>
      </form>

      {/* Só a Esfera pode ficar de fora; as outras quatro são obrigatórias. */}
      {aberta === "esfera" && conta?.status !== "concluida" && (
        <form
          action={acaoNao}
          className="space-y-3 rounded-xl border border-gray-100 bg-white/90 p-5 shadow-sm sm:p-6"
        >
          <input type="hidden" name="token" value={token} />
          {conta?.status === "nao_criada" ? (
            <p className="text-sm leading-relaxed text-gray-700">
              Você marcou que não conseguiu criar a conta Esfera. Se conseguir depois, é só
              preencher o login e a senha acima e salvar.
            </p>
          ) : (
            <>
              <p className="text-sm leading-relaxed text-gray-700">
                Tentou e não conseguiu criar a conta da Esfera? Tudo bem: só ela pode ficar de
                fora. Use o botão abaixo para seguir para a cartilha.
              </p>
              {estadoNao.erro && <p className="text-sm text-red-600">{estadoNao.erro}</p>}
              <button
                type="submit"
                disabled={pendenteNao}
                className="rounded-md border border-gray-400 bg-white px-4 py-2 text-sm font-semibold text-gray-800 transition-colors hover:bg-gray-50 disabled:opacity-50"
              >
                {pendenteNao ? "Registrando…" : "Não consegui criar essa conta Esfera"}
              </button>
            </>
          )}
        </form>
      )}
    </div>
  );
}
