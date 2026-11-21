> **Repositório público.** Este repo contém só código. Dados de clientes, segredos e IDs de projeto
> ficam fora: configure tudo em variáveis de ambiente / GitHub Secrets (veja `.env.example`).
> Nos workflows, `LOG_SEGURO=1` + `src/sitecustomize.py` descartam toda saída de log (logs do Actions
> de repo público são abertos). Nunca faça commit de CSV, PDF, prints ou exportações de clientes.

# LF Viagens — Checagem automática de voos

Acompanha os voos emitidos pela agência e avisa no Telegram quando algo muda:
horário alterado pela companhia, voo cancelado, ou localizador que deixou de
existir.

**Em produção:** roda sozinho às 7h e 19h, mais a malha às 8h — via
`LaunchAgents` (não mais `cron`, ver [Agendamento](#agendamento)). LATAM, GOL
e AZUL no ciclo automático (GOL parcial, por causa do reCAPTCHA); as demais
por painel de conferência. Se o Mac estiver desligado no horário, o `vigia`
recupera assim que ele ligar.

---

## Uso diário

Nada a fazer — o sistema roda sozinho e avisa no Telegram. Os comandos abaixo
são para quando você quiser olhar ou intervir.

```bash
.venv/bin/python src/rodada.py            # rodada completa, agora
python3 src/painel.py --abrir             # painel de conferência manual
.venv/bin/python src/checar_malha.py      # malha: a rodada do dia (rotação)
.venv/bin/python src/checar_azul.py       # Azul (--loc PNR para uma só)
.venv/bin/python testes/rodar_testes.py   # valida os leitores (offline)
```

### O que chega no Telegram

| Quando | O quê |
|---|---|
| 07h | alertas novos + resumo diário |
| 19h | alertas novos + recapitulação dos críticos do dia |
| qualquer hora | aviso se a checagem falhar ou o sistema ficar cego |

### Link pronto e aba Urgente (desde 31/07/2026)

Toda reserva com alteração detectada já chega com o link de consulta
**pronto para clicar** — no Telegram e no `conferencia.html`:

```
🟠 TSTAOX (GOL) — horario alterado
   1969 NAT→GIG · CRM 10:00 -> companhia 11:00
   👤 Maria Aparecida Lopes
   🔗 abrir reserva
```

O link usa a mesma regra do painel (PDF do bilhete > montado com o que o CRM
tem — ver `painel.link_para`). Companhia sem conector (TAP, Copa…) ou sem
sobrenome no CRM fica sem link mesmo; nada é inventado.

O `conferencia.html` ganhou uma aba **🚨 Urgente**, com as reservas alteradas
nessa rodada e o link pronto — ao lado da aba de conferência manual que já
existia. Ela reflete só a rodada mais recente: o que já foi avisado não
volta, mesmo que o operador não tenha clicado ainda (mesma regra de
não-repetir-alerta do resto do sistema).

O resumo diário das 19h também passou a avisar quantas reservas estão
paradas esperando conferência manual, com a mais próxima do embarque —
antes nada cutucava o operador a abrir o painel quando uma reserva GOL ficava
presa no reCAPTCHA em toda tentativa:

```
🕘 4 reserva(s) aguardando conferência manual — mais próxima: TSTADX (GOL),
embarca em 3 dia(s).
```

---

## Arquivos gerados (`dados/`)

| Arquivo | Conteúdo |
|---|---|
| `voos_atual.csv` | foto mais recente — abre no Excel |
| `pendencias_*.csv` | voos que **não dá** para checar, com o motivo |
| `pendencias_<cia>.json` | reservas que a checagem automática não conseguiu conferir — o painel as inclui |
| `conferencia.html` | painel com aba Urgente (alterações da rodada) + conferência manual, links prontos |
| `links_reservas.csv` | índice de links extraídos dos PDFs |
| `voos_*.csv` | histórico diário (45 dias) |

O banco `voos.db` guarda o histórico. É ele que permite dizer *"isso mudou
desde ontem"* — CSV sozinho não compara.

---

## Configuração

```bash
cp .env.example .env
```

Preencher: `MILHASFLOW_EMAIL`, `MILHASFLOW_SENHA`, `MILHASFLOW_ANON_KEY`
(instruções dentro do arquivo), `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`
(use `python3 src/descobrir_chat.py` para descobrir o chat).

O `.env` fica só na máquina, com permissão 600, e está no `.gitignore`.
**Nunca envie esse arquivo por e-mail, WhatsApp ou chat.**

### Agendamento

Desde 31/07/2026, roda por **`LaunchAgents`** (`~/Library/LaunchAgents/`), não
mais por `cron`:

| Label | Horário | Comando |
|---|---|---|
| `com.lfviagens.rodada-manha` | 7h | `rodada.py --resumo` |
| `com.lfviagens.vigia` | login + a cada 30 min | ver **Vigia**, abaixo |

**Desde 07/08/2026, uma rodada só por dia** (decisão do proprietário: economiza
consulta de API e simplifica o agendamento). A malha entrou pra dentro da
própria `rodada.py` — roda logo depois dos portais, na mesma execução das 7h,
em vez de um `LaunchAgent` separado às 8h. A rodada da noite (19h,
`--recapitular`) foi desligada; a flag continua existindo em `rodada.py` pra
quem quiser rodar à mão.

```bash
launchctl print gui/$(id -u)/com.lfviagens.rodada-manha   # status e próximo disparo
tail -f dados/rodada.log                                  # acompanhar em tempo real
```

#### Por que saiu do cron

O problema nunca foi o `cron` em si — foi o escopo da permissão que ele
precisava. O daemon do `cron` roda com um **Acesso Total ao Disco** separado
do Terminal, e a pasta de PDFs no iCloud (ver seção **LATAM**) ficava
bloqueada só na execução automática, sem ninguém perceber até revisar os
logs. `LaunchAgent` resolve isso de um jeito mais restrito: dá pra conceder
essa permissão a um binário específico (o Python do `venv`), em vez de ao
daemon inteiro, que rodaria qualquer tarefa agendada por qualquer software —
escopo bem mais apertado.

A permissão foi concedida ao binário **real** por trás do `venv`, não ao link
simbólico (o painel de permissões não deixa selecionar links):

```
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9
```

Isso é o Python compartilhado das Command Line Tools — não é exclusivo deste
projeto, mas ainda assim bem mais restrito do que liberar o `cron` inteiro.
Isolamento total exigiria um Python dedicado (via `pyenv` ou instalador
oficial) só para o `venv` da agência.

#### Vigia — o que fazer quando o Mac esteve desligado

`LaunchAgent` recupera sozinho um horário perdido quando o Mac só estava
**dormindo**, mas não quando estava **desligado de verdade**: o horário passa
e nada dispara, porque o próprio agendador não estava rodando para notar.

`src/agenda.py` grava em `.agenda.json` (raiz do projeto) se o resumo das 7h,
a malha das 8h e o recap das 19h já rodaram hoje — só marca quando terminou
de verdade (rodada parcial, seca, ou com Telegram falhando não conta; o vigia
tenta de novo). `src/vigia.py` compara a hora atual com os três horários: o
que já passou e ainda não rodou hoje, dispara na hora. Roda no login/boot **e**
a cada 30 min — repetir em dia não faz nada.

Prático: Mac desligado às 7h, ligado só às 14h → a checagem da manhã roda
sozinha ao ligar, sem esperar o próximo 7h do dia seguinte.

Mesmo assim, ficar mais de 30h sem nenhuma rodada bem-sucedida (Mac apagado
o dia inteiro, por exemplo) ainda gera o aviso de "sistema ficou cego" — ver
**Falha nunca é silenciosa**.

---

## De onde vêm os dados

O MilhasFlow é um front-end que conversa direto com um backend **Supabase**
(PostgREST). O sistema autentica com o login da agência e lê as mesmas tabelas
que a tela *Acompanhamentos → Voos*:

- `reminders` — um registro por trecho (localizador, cia, nº do voo, aeroportos, horários)
- `emissions` — a venda (cliente, passageiros, valor, tags)

Não há scraping de tela nem extensão: é a própria API da plataforma.

### ⚠️ O banco grava UTC

Os portais mostram a hora local de cada aeroporto. Tratar UTC como local
gerava alerta de "horário alterado" em **100% dos voos**. `fusos.py` converte
por aeroporto — não dá para usar UTC-3 global, a base tem CDG, LHR, BKK, DOH.

Aeroporto fora do mapa de fusos **bloqueia a checagem** daquele voo, em vez de
produzir horário errado em silêncio.

---

## Conectores

| Cia | Como | Depende de PDF? | Situação |
|---|---|---|---|
| **LATAM** | API `/bff/mytrips/v1/order/…` via deep link do PDF | sim | ✅ no ciclo — 16/16 em 30/07 |
| **GOL** | página de detalhes, dados do CRM | não | ✅ no ciclo — 6/8 em 30/07, reCAPTCHA não barrou |
| **AZUL** | API `/canonical/api/booking/v5/bookings/…`, dados do CRM | não | ✅ no ciclo — 4/4 em 30/07 |
| TAP, Copa, AF, Qatar | — | — | painel manual |
| **todas** | **malha por nº de voo + data** | não | ✅ validada na API real; 1×/dia por rotação |

Os conectores acima são **por reserva**; a malha é **por voo**. São fontes
complementares, e é a soma que fecha o monitoramento — ver a seção Malha.

### Cadência — quem é conferido em cada rodada

`rodada.py` percorre as três companhias e só consulta a que está vencida, pela
proximidade do embarque:

| Embarque em | Reconsulta a cada |
|---|---|
| até 2 dias | 6h |
| até 7 dias | 12h |
| até 30 dias | 24h |
| mais longe | 7 dias |

#### ⚠️ A cadência se mede por leitura, não por alerta

Até 30/07/2026 ela olhava o **último alerta** daquela companhia. Conector que
roda e não acha nada não gera alerta nenhum — então uma companhia sem novidade
ficava para sempre em *"nunca checado"* e era reconsultada em toda rodada.
Desperdício na LATAM e na GOL, e risco real na Azul, que já limitou o IP da
agência uma vez.

Hoje quem marca a checagem é a **observação** (`db.registrar_observacao`), que é
gravada mesmo quando está tudo certo.

### LATAM

A busca manual é barrada por Akamai. O que funciona é o **deep link do PDF**
(`?orderId=…&lastname=…`), que entra direto e vale inclusive para reserva de
cliente que não é o titular da conta logada.

O sistema **não lê a tela** — captura a API que a página consome, que traz
todos os trechos já estruturados e com o status IATA de cada um:

| Status | Significado |
|---|---|
| `HK` `KK` `RR` | confirmado |
| `TK` `WK` `SC` | a companhia alterou |
| `UN` `HX` `UC` `NO` | trecho cancelado |

**O PDF da LATAM não contém o PNR de 6 caracteres**, só o número de compra. A
ligação com o CRM é por **nº do voo + data** — sobrenome não serve, SILVA e
MELO se repetem entre clientes.

#### A pasta do iCloud e a permissão do agendador

Os PDFs ficam em `~/Library/Mobile Documents/…`, que o macOS protege por **TCC**.
Rodando à mão funciona (o Terminal tem permissão); pelo agendador — antes
`cron`, agora `LaunchAgent` —, só se o binário que executa o Python também
tiver a permissão. Sem ela, o erro engana:

```
PermissionError: [Errno 1] Operation not permitted
```

Não é "pasta faltando": `os.path.isdir` devolve **True** (o `stat` passa) e só o
`listdir` estoura. Por isso o guarda de `isdir` não protegia nada, e a rodada
das 7h e 19h morria inteira antes de checar um voo — bug ativo em **toda**
execução automática entre 29/07 e 30/07/2026, corrigido em 31/07/2026 dando
Acesso Total ao Disco ao Python do `venv` (ver **Agendamento**).

Mesmo com a permissão concedida, a checagem **não depende só dela**: se o
macOS negar a pasta por qualquer motivo (permissão revogada, PDF ainda
sincronizando do iCloud), cai no índice `dados/links_reservas.json`, que fica
dentro do projeto (sem TCC) e foi extraído desses mesmos PDFs. Conferido: as
duas fontes dão os **mesmos 35 deep links, com as mesmas URLs**.

O limite do índice é honesto e a rodada avisa: PDF salvo **depois** do último
`indexar_links.py` não está nele. Se o índice passar de 7 dias, ela pede para
você rodar:

```bash
python3 src/indexar_links.py
```

### GOL

O deep link **se envia sozinho** — não clicar em nada. Basta abrir e esperar a
URL virar `/minhas-viagens/detalhes-da-viagem`.

Não depende de PDF: localizador, origem e sobrenome já estão no CRM.

**Causa da instabilidade, identificada em 29/07/2026.** A página chama
`booking-api.voegol.com.br/api/pnrBnpl/pnr-bnpl-validation-v2`, e a GOL exige
score de **reCAPTCHA Enterprise** nesse endpoint. Navegador automatizado tira
score baixo — e o score varia por sessão, então parte das consultas passa e
parte leva:

```
500  {"success":false,"error":{"message":"Error recaptcha: score recaptcha is fail"}}
```

Medido: **4 de 8 localizadores passaram**, 3 barrados pelo reCAPTCHA, 1 com
erro real da GOL (`Failed to obtain a pnr-BNPL`).

A tela esconde tudo isso: mostra só "Houve um erro. Tente novamente mais
tarde.", limpa a query string e devolve o formulário vazio — o que por muito
tempo pareceu "página que não carregou" e fez a hipótese de reCAPTCHA ser
descartada por engano.

Não se tenta contornar o reCAPTCHA. Derrubar o IP da agência custa mais do que
conferir a mão, e no Chrome normal do operador os links funcionam. Então:

- o que passa é conferido automaticamente e vale
- `checar_gol.py` reconhece a recusa em ~6s (antes gastava 66s por reserva
  esperando uma URL que nunca ia mudar) e manda a reserva para o painel —
  nenhuma sai do monitoramento em silêncio
- 3 recusas **seguidas** param a rodada: sinal de que a GOL fechou de vez, e
  insistir só arrisca o IP
- a conferência acontece em `python3 src/painel.py --abrir`

### AZUL

Como a Gol, não depende de PDF — e é a única que **não pede sobrenome**: o link
leva só PNR e aeroporto de origem.

```
/br/pt/home/minhas-viagens/confirmacao?pnr=IJ56KL&origin=BSB
```

**Validado em 30/07/2026: 4 de 4 localizadores lidos.** Abrir esse link faz a
página autenticar e chamar a API canônica, que é de onde lemos:

```
b2c-api.voeazul.com.br/canonical/api/booking/v5/bookings/<PNR>
```

O sistema **não lê a tela** — o texto da página é 90% oferta de hotel, cupom e
assento. A API traz o itinerário inteiro estruturado.

| Campo | Serve para |
|---|---|
| `data.info.status` | `Confirmed`; qualquer coisa com "cancel" vira cancelamento |
| `journeys[].segments[].identifier` | voo, rota, `std`/`sta` |
| `isReaccommodation` | a companhia remanejou o trecho |
| `stops`, `legs` | paradas e escalas |

#### ⚠️ Aqui os horários são LOCAIS

`std` veio `2026-08-20T20:35:00` para o voo que o CRM tem como 20:35 em REC.
Diferente do banco do MilhasFlow, que grava UTC, **não se converte nada** —
converter geraria "horário alterado" em 100% dos voos.

#### Conexão não atrapalha, ao contrário da GOL

Cada trecho vem separado no JSON, então não existe o risco de o leitor fundir
dois e inventar "rota alterada". Por isso `azul.py` **não** tem a regra de
conexão que a GOL precisa ter. Comprovado com `TSTAAX`, de 4 trechos.

Por ter sido ela a bloquear o IP, é o conector mais cauteloso dos três:

- a quarentena é conferida **antes de abrir o Chrome**
- **2** recusas seguidas param a rodada (a Gol tolera 3)
- HTTP 403/429 em **qualquer** endpoint → quarentena imediata e rodada
  interrompida
- teto de 20 reservas por rodada, folga sobre o limite de 40/h do `limitador`

#### Dois erros cometidos na validação, ambos com teste de regressão

**1. 404 de endpoint acessório derrubava reserva boa.** A página chama
`/resources/api/weather/v1/forecast/…` (previsão do tempo do destino), que
responde 404 ou 400 sem que a reserva tenha problema. Tratar qualquer 404 como
recusa mandou 2 reservas intactas ao painel e parou a rodada por "2 recusas
seguidas". Agora só erro em endpoint **essencial** (`booking`, `authentication`)
conta — mas 403/429 continua valendo em qualquer um, porque bloqueio de IP não
escolhe rota.

**2. 30s de espera não bastavam.** Reserva de 4 trechos dispara 6 chamadas de
API e não chegava a tempo, aparecendo como "não trouxe a reserva" — falso
negativo. Subiu para 60s, e a mensagem agora separa *"não respondeu em Xs"* de
*"respondeu sem itinerário"*: são coisas diferentes e chamar as duas pelo mesmo
nome esconde qual está acontecendo.

Para diagnosticar uma reserva sem gastar consulta com as outras:

```bash
.venv/bin/python src/checar_azul.py --loc TSTAAX --capturar
```

---

## Malha — a fonte que cobre 100% dos voos

Os três conectores acima consultam **reservas**, e cada um tem seu pedágio:
LATAM exige PDF, GOL topa no reCAPTCHA, Azul bloqueou o IP. TAP, Copa, AF e
Qatar não têm conector nenhum.

A malha inverte a pergunta. Em vez de *"como está a reserva TSTADX?"*, pergunta
**"o voo G3 1681 do dia 03/08/2026 saiu do horário que o CRM diz?"** — e para
isso o CRM já tem tudo: número do voo, trecho e data estão preenchidos em
**48 de 48** voos futuros. Sem localizador, sem sobrenome, sem PDF, sem sessão,
sem captcha.

```bash
.venv/bin/python src/checar_malha.py               # a rodada do dia
.venv/bin/python src/checar_malha.py --plano       # mostra o que faria, sem gastar
.venv/bin/python src/checar_malha.py --orcamento 40  # gastar mais hoje
.venv/bin/python src/checar_malha.py --tudo        # ignora a rotação
.venv/bin/python src/checar_malha.py --cia GOL     # só uma companhia
.venv/bin/python src/checar_malha.py --seco        # não grava alerta
```

A rodada **não varre a lista** — ela escolhe. Ver *Rotação*, abaixo.

Uma chamada por **nº de voo + data**, não por reserva: duas reservas no mesmo
voo custam uma consulta só. Nos dados de hoje, 48 voos viram 46 consultas.

Validado contra a API real em 29/07/2026: **7 voos da faixa de 15 dias, LATAM e
GOL, todos batendo com o CRM** — nenhum falso positivo.

### O que ela vê e o que ela não vê

| Vê | Não vê |
|---|---|
| horário alterado pela companhia | PNR cancelado |
| rota alterada | passageiro remarcado para outro voo |
| voo cancelado (`Canceled`) / desviado / atrasado | bilhete cancelado |
| voo que deixou de operar naquela data | qualquer coisa no nível da **reserva** |

O ponto cego é real: se a companhia tira o passageiro do voo, o voo continua na
malha igual — só o passageiro saiu dele. **Por isso a malha não substitui os
conectores de portal**, ela cobre o furo de cobertura deles. As duas fontes
juntas é que fecham o monitoramento.

### As três armadilhas, e como cada uma foi fechada

**1. Resposta vazia não é cancelamento.** O endpoint devolve `204` tanto para
"voo não opera nessa data" quanto para "data fora da cobertura do seu plano".
Tratar isso como cancelamento transformaria todo voo distante em alarme falso.
Resposta vazia entra em *"sem malha publicada"*, nunca em alerta — e o resumo
diz isso em voz alta.

**2. `Canceled`, com um L só.** É o valor do enum `FlightStatus` no contrato
oficial. `Cancelled` (dois L) não existe na API, e existe um teste que falha se
alguém "corrigir" a grafia.

**3. Hora local, nunca UTC.** A API entrega `scheduledTime.local` e
`scheduledTime.utc`. O leitor usa **sempre** o `local`, que é o que o CRM
guarda em `embarque_local` — tratar UTC como local foi o bug que gerou alerta
em 100% dos voos (ver a seção de fusos). O teste usa um voo em que os dois
diferem em 3h justamente para travar isso.

Quando a companhia mexe no horário, ela publica `revisedTime` e o
`scheduledTime` continua o original. O leitor compara o **revisado** contra o
CRM e ainda registra o de–para no alerta.

E onde a malha não pode afirmar, ela cala a boca: horário só estimado
(`quality` sem `Basic` nem `Live`), IATA ausente, ou formato de hora
inesperado ⇒ passa só o status explícito, sem comparar itinerário. Mesma regra
do conector da Azul.

### Configuração

Preencha `MALHA_API_KEY` no `.env` (instruções no `.env.example`). **Sem a
chave, o resto do sistema segue normal** — só essa fonte fica desligada.

O fornecedor de referência é a **AeroDataBox**, e os nomes de campo em
`malha.py` saem do **OpenAPI oficial** dela, não de chute. Ela é vendida por
canais com base e cabeçalho diferentes, então os dois vêm do `.env` — trocar de
fornecedor não encosta em `malha.py` nem em `checar_malha.py`.

Em uso aqui: **RapidAPI**.

```
MALHA_API_URL=https://aerodatabox.p.rapidapi.com
MALHA_API_HEADER=x-rapidapi-key
```

O RapidAPI exige um segundo cabeçalho, `x-rapidapi-host`. Ele **não** é
configurado: sai do próprio `MALHA_API_URL`, que já tem que estar certo de
qualquer forma. Uma linha a menos para errar.

#### Cloudflare 1010: o 403 que não é a chave

A origem da AeroDataBox fica atrás de Cloudflare, que **bloqueia o User-Agent
padrão do Python** (`Python-urllib/3.x`) com erro `1010
browser_signature_banned`. O sintoma engana: HTTP **403**, igual a chave
inválida — só que a assinatura está em ordem e a cota nem é consumida.

`provedor_malha.USER_AGENT` identifica a agência honestamente e resolve. Não é
disfarce de navegador: é dizer quem somos, que é o que faltava. O diagnóstico de
403 agora distingue as duas causas em vez de mandar você conferir uma chave que
está certa.

### Cota — é ela que manda na cadência

O endpoint de voo é **TIER 2: 2 unidades por consulta**, não 1. O plano BASIC do
RapidAPI dá **600 unidades/mês = 300 consultas**. Medido, não estimado.

| Horizonte | Consultas | Unid./rodada | Rodadas/mês |
|---|---|---|---|
| 15 dias | 7 | 14 | ~43 |
| 30 dias | 19 | 38 | ~16 |
| 60 dias | 29 | 58 | ~10 |
| tudo (120) | 46 | 92 | **6,2** |

Conferir os 47 voos futuros todo dia pediria 2.820 unidades/mês. Cabem **10
consultas por dia**, e é isso que define o desenho.

### Rotação — quem é conferido hoje

A rodada não varre a lista: gasta o orçamento do dia nos voos mais atrasados.
Um agendamento diário basta — a malha roda dentro da `com.lfviagens.rodada-manha`
(7h — ver **Agendamento**), porque a escolha de quem conferir é dela.

A prioridade vem da operação da agência, não de palpite:

| Antecedência | Cadência de referência | Por quê |
|---|---|---|
| **menos de 8 dias** | **não confere** | a equipe já acompanha pelo CRM, que abre o voo para check-in e manipulação |
| 8–30 dias | a cada 3 dias | pouco tempo para reagir se mudou |
| 31–90 dias | a cada 7 dias | onde a alteração costuma nascer |
| 90+ dias | a cada 14 dias | muda, mas dá tempo — ver abaixo |

**A proporção 3 : 7 : 14 é fixa; a escala não.** A carteira muda toda semana —
voo novo entra, voo antigo embarca — então intervalo cravado ou deixaria crédito
parado ou estouraria a cota no dia 20. `malha.ajustar_faixas()` multiplica os
três intervalos pelo mesmo fator, preservando a relação que a agência escolheu:

| Carteira | Voos | Faixas ajustadas | Fator |
|---|---|---|---|
| ¼ da de hoje | 11 | 2d / 4d / 8d | 0,60 |
| metade | 23 | 2d / 5d / 9d | 0,67 |
| **hoje** | **47** | **3d / 7d / 13d** | **0,96** |
| o dobro | 94 | 6d / 13d / 27d | 1,91 |
| 5× | 235 | 14d / 34d / 67d | 4,79 |
| 10× | 470 | — | ⚠️ não cabe: avisa |

`FATOR_MIN = 0.6` evita gastar crédito conferindo o mesmo voo todo dia (a malha
não muda tanto); `FATOR_MAX = 5.0` faz a rodada **dizer que não cabe** em vez de
esticar até o intervalo virar dois meses em silêncio.

Aguenta a carteira crescer **5×** antes de precisar de plano maior.

O ponto que parece contraintuitivo: voo distante é conferido **menos** vezes,
mesmo sendo onde a mudança nasce. Isso não perde alteração nenhuma, porque a
comparação é sempre **contra o CRM**, nunca contra a checagem anterior. Intervalo
maior atrasa a notícia, não a perde — e um voo a 120 dias que mudou continua
mudado quando a rotação chegar nele. O que decide a frequência é **quanto tempo
sobra para reagir**, não a chance de mudar.

Se preferir o contrário, é uma linha: `malha.FAIXAS`.

Simulação de 30 dias com os voos de hoje (`--plano` não gasta cota):

| Faixa | Voos | Conferido | Pior intervalo |
|---|---|---|---|
| 8–30 dias | 18 | 3,8×/mês | 5 dias |
| 31–90 dias | 21 | 5,9×/mês | 8 dias |
| 91+ dias | 8 | 3,1×/mês | 15 dias |

**436 de 600 unidades (73%)** e nenhum voo acima de 7 dias sem conferência. Os
27% de folga são de propósito: conforme a agência vende, entram voos novos.

O estado da rotação vive na tabela `malha_checagens`. A data é anotada **assim
que a consulta é paga**, mesmo que a leitura não renda nada — senão um voo
problemático seria reconsultado todo dia e comeria a cota sozinho.

### Os freios

Estourar a cota no dia 10 é pior que não ter a fonte:

- **o orçamento do dia sai do saldo real da API**, não de uma constante:
  `(unidades_restantes − reserva) ÷ dias até renovar`. Teste manual, rodada de
  outra máquina, qualquer gasto por fora já entra na conta sozinho. O último
  saldo fica na tabela `malha_cota`; `ORCAMENTO_DIARIO = 20` só vale na primeira
  rodada, antes de a API ter informado nada
- e vale **por dia**, não por invocação: rodar o script três vezes numa tarde
  não gasta três vezes o teto. O gasto do dia sai da tabela `malha_checagens`
- `RESERVA_UNIDADES = 40` — a rodada para se o saldo do mês cair abaixo disso, e
  diz quantos voos ficaram sem conferência
- `MALHA_DIAS` (120) descarta voo muito distante, que raramente tem malha publicada
- HTTP 429 é lido pelos seus dois sentidos: excesso **por segundo** espera e
  repete (não custa unidade); cota do período esgotada para a rodada

O resumo mostra `chamadas HTTP` e `cota restante` separados de propósito —
retentativa conta como chamada e não é cobrada, e quem diz a verdade sobre custo
é o saldo do fornecedor.

Desde 07/08/2026, entrou no `rodada.py` — chamada como uma etapa a mais,
depois dos portais, na mesma rodada das 7h (ver **Agendamento**). Continua
1×/dia porque é a própria cadência da malha que manda nisso, não o
agendamento: mesmo rodando duas vezes por dia, `checar_malha.py` não gastaria
cota extra fora do orçamento diário.

---

## Índice de links dos PDFs

```bash
python3 src/indexar_links.py     # 100% local, não acessa site
```

Cada bilhete traz o link que a própria companhia gerou. Vale mais que qualquer
URL montada por nós — é o formato oficial e sobrevive a mudanças no site.

Descartados: **links do Smiles** (exigem login e não mostram status) e páginas
de bagagem, assento e cartão de embarque.

### ⚠️ A origem do link envelhece

O link é gerado na emissão e congela a origem da ida. Numa reserva de ida e
volta consultada depois da ida, ele aponta para um trecho que já voou — e a
consulta falha sem erro claro. O sistema reescreve a origem para o **primeiro
trecho ainda não voado**.

> Exemplo real: `TSTADX` tinha `origem=GRU` no PDF (ida de julho). Com a ida
> voada, a consulta correta é `origem=NAT`, a volta de agosto.

---

## As regras que evitam alarme falso

Todas nasceram de erro real cometido em 29 e 30/07/2026.

| Regra | Erro que ela impede |
|---|---|
| "não encontrei" nunca vira "cancelado" | 16 falsos cancelamentos |
| identificar a reserva antes de comparar | 68 alertas contra a base inteira |
| viagem já realizada sai do escopo | cia reusa nº de voo todo dia |
| leitura com conexão suprime comparação | 4 "rota alterada" em reserva intacta |
| voo e rota batem mas data não → **revisar** | remarcação confundida com outra viagem |
| teto de 15 alertas por rodada | enxurrada é bug, não 40 voos cancelados |
| mesmo achado por 2 fontes = 1 alerta | malha + portal avisando o mesmo voo duas vezes |
| fontes que **discordam** → "confira", não "mudou" | eleger uma fonte em silêncio e alertar errado |
| aviso explícito passa mesmo sem confiança | cancelamento silenciado por cautela |

### Duas fontes achando a mesma coisa

A malha olha por **nº de voo + data**; os conectores olham **por reserva**. São
complementares de propósito, então o mesmo voo alterado aparece nas duas — e em
30/07/2026 o `AD 2660` da `TSTAAX` gerou dois registros idênticos, um da malha e
outro do portal da Azul, prontos para virar duas mensagens no Telegram.

Duas fontes concordando não é ruído, é **confirmação**. Em vez de esconder a
segunda, a mensagem passa a dizer quem confirmou:

```
🟠 TSTAAX — rota alterada
   AD 2660 CNF→POA · 2026-09-13 17:10 · origem: CRM CNF -> companhia VCP
   · confirmado por malha da companhia e portal Azul
```

O que não pode é o operador receber a mesma coisa duas vezes e achar que são
dois problemas. Os dois registros são marcados como notificados juntos — marcar
só o representante deixaria o outro pendente para sempre.

### Duas fontes discordando

O caso oposto, e mais perigoso. Em 30/07/2026 a malha disse que o `AD 4626` sai
**20:20**; a API da Azul e o CRM dizem **20:40**. O alerta da malha foi para o
Telegram sozinho.

O motivo é sutil: **o conector só gravava quando discordava do CRM**. Quando ele
concorda e a malha diverge, o conector fica calado e nada sinaliza a
contradição — o operador recebe um número só, sem saber que a outra fonte diz
outra coisa.

A correção foi passar a registrar **o que cada fonte observou**, e não apenas
quando ela reclama (tabela `observacoes`, uma linha por voo × fonte). É a
leitura que *concorda* com o CRM que permite dizer que a outra fonte está fora
da linha.

Quando duas fontes recentes discordam, o alerta sai com os dois valores e sem
eleger vencedor:

```
🟡 AB12CD — fontes divergem
   AD 4626 CGH→REC · 23/08 20:40 · malha da companhia 20:20 · portal Azul 20:40 — confira
```

Amarelo de propósito: não é mudança confirmada, é dúvida. Por isso também fica
**fora** da recapitulação de críticos da noite. `situacao` não entra na
comparação — cada portal tem vocabulário próprio (`Confirmed`, `Confirmada`,
`HK`) e comparar texto cru acusaria divergência em reserva intacta.

Só entram leituras das últimas 48h: comparar leitura velha com leitura nova
acusaria divergência onde houve, na verdade, uma mudança que as duas fontes já
registraram em momentos diferentes.

### Conector não tira ninguém do painel sem rede de segurança

Quando Azul e GOL ganharam conector, saíram da lista de conferência manual:
repetir lá o que a máquina já conferiu faz o operador trabalhar duas vezes.

Só que consulta **falha** — a API da Azul não respondeu em 60s numa das quatro
reservas no primeiro teste, e a GOL deixou 2 de 8 para trás. Se a reserva
sumisse das duas pontas, ficaria fora do automático **e** fora do painel, sem
ninguém olhando.

Por isso cada conector publica `dados/pendencias_<cia>.json` com o que **não**
conseguiu conferir, e o painel inclui exatamente esses. Três regras fecham o
buraco:

| Situação | O painel mostra |
|---|---|
| conector conferiu a reserva | nada — já está coberta |
| conector falhou nessa reserva | a reserva |
| **arquivo de pendência não existe** | **a companhia inteira** |

A terceira é a que importa: sem arquivo, ou o conector nunca rodou ou quebrou
antes de publicar. Nos dois casos não há base para dizer que a carteira está
conferida — na dúvida o painel mostra a mais, nunca a menos.

Rodada parcial (`--loc`, `--limite`, `--capturar`) **preserva** a pendência
anterior: quem não foi consultado não virou "conferido".

A LATAM fica fora desse mecanismo de propósito — o conector dela publica
`sem_pdf_latam.csv`, que tem outra semântica (reserva sem PDF é *não checável*,
não *falhou ao checar*).

---

## Falha nunca é silenciosa

O sistema distingue **"está tudo bem"** de **"não consegui olhar"** — confundir
os dois é o pior resultado possível.

- Sincronização falhou → a rodada **aborta e avisa**, em vez de mandar um
  "0 alterações" enganoso
- **Checagem de companhia falhou → avisa no Telegram** e as outras seguem
- Exceção não tratada → vira aviso no Telegram
- Etapa travada → timeout de 45 min
- **Mais de 30h sem rodada** → a próxima diz quantas horas o sistema ficou cego

### O buraco que existia até 30/07/2026

`rodada.py` chamava a checagem da LATAM e **descartava o retorno**. Naquela
manhã ela morreu com `PermissionError` na pasta do iCloud e a rodada seguiu,
mandando o resumo diário normalmente — as 16 reservas LATAM passaram como
conferidas sem ninguém ter olhado para elas.

Hoje o retorno é conferido e a falha vira mensagem, com o texto dizendo o que
importa: *"não quer dizer que está tudo certo, quer dizer que o sistema não
conseguiu olhar"*.

Uma companhia que falha **não** aborta a rodada: portal fora do ar deixa a
checagem parcial, e as outras companhias e os alertas já apurados continuam
valendo. Só o `sync` aborta, porque sem ele não há o que comparar.

Nem todo retorno diferente de zero é falha: `checar_azul.py` sai com **código
2** quando a Azul está em quarentena, e isso é o limitador funcionando. Alertar
sobre isso a cada rodada transformaria a proteção em ruído.

---

## Ritmo e bloqueio

`limitador.py` controla o intervalo entre consultas a cada companhia. O estado
fica em **arquivo**, não em memória, para valer também entre processos — dois
scripts seguidos respeitam o mesmo intervalo.

> Existe porque em 29/07/2026 a Azul limitou o IP da agência depois de vários
> acessos automatizados seguidos, feitos por scripts que não passavam pelo
> espaçamento. Se um site sinalizar bloqueio, o domínio entra em quarentena
> automática e a rodada para — insistir transforma limite temporário em
> bloqueio longo.

**Nunca rodar headless.** O anti-bot da LATAM detecta e a API não responde
(34 de 34 falharam). O `--invisivel` abre janela real fora da tela.

O perfil do Chrome é **recriado a cada rodada**: perfil acumulado chegou a
247 MB e passou a derrubar o navegador no meio da execução.

---

## Testes

```bash
.venv/bin/python testes/rodar_testes.py
```

Rodam contra páginas **reais** salvas em `testes/paginas/`, sem acessar site
nenhum. Cada caso corresponde a um erro que o sistema realmente cometeu.

Os casos da **Azul** rodam contra a resposta real da API (`azul_pm99tj.json`,
capturada em 30/07/2026), com os dados do passageiro anonimizados e o itinerário
intacto.

Rode antes de mexer em qualquer leitor.

---

## Faxina automática

No fim de cada rodada (`manutencao.py`):

| O quê | Retenção |
|---|---|
| CSVs diários e pendências | 45 dias |
| Backups do banco | 7 dias |
| Histórico já notificado | 365 dias |
| Logs | rotaciona em 2 MB |

Nunca toca em `voos.db`, `voos_atual.csv` nem em alerta ainda **não** notificado.

---

## Módulos

```
config      lê o .env
milhasflow  autentica e busca no Supabase
sync        monta os voos, grava e gera os CSVs
db          SQLite + diff contra a leitura anterior + observações por fonte
fusos       UTC → hora local do aeroporto
qualidade   decide se um voo é checável e com que prioridade

pdfs         extrai links de dentro dos PDFs
indexar_links  índice único de links por reserva
painel       HTML de conferência manual (aba Urgente + conferência), monta o link de cada reserva

navegador   Chrome real, com limitador embutido
limitador   ritmo e quarentena por domínio
provedor_malha  única parte que fala com a API de malha
latam/gol/azul/malha  leitores puros (texto/JSON → dados)
comparacao  cruza companhia × CRM
checar_*    orquestradores (por companhia; malha cobre todas)

rodada      o que o agendador chama
alertas     Telegram, com link e passageiro prontos no alerta
manutencao  faxina
agenda      registra o que já rodou hoje (usado pelo vigia)
vigia       dispara o que ficou pra trás quando o Mac esteve desligado
```

---

## Área de cedentes (convite)

Portada do trademiles (`lflucasm/lf_viagensTradeM`, `app/convite/[code]`). Cada
colaborador tem **um link de convite**; quem abre o link se cadastra como
titular, aceita o termo e é levado ao **cadastro guiado das contas** — uma aba
por programa, progresso salvo, sem precisar de login.

```
/cedentes            painel: meu link, links da equipe (admin), lista de titulares
/cedentes/<id>       painel: ficha, credenciais (admin), aprovar/rejeitar
/cedentes/termos     admin: publica versão nova do termo
/convite/<codigo>    público: cadastro do titular + aceite do termo
/cedente/<token>     público: passo a passo das contas, retomável
```

O ciclo inteiro: colaborador manda o link → titular se cadastra e aceita o
termo → cria as contas passo a passo, uma aba por programa, gravando login e
senha de cada uma → admin confere na ficha → **aprovar envia pro MilhasFlow**.

As duas rotas públicas ficam **fora do matcher do `proxy.ts`** — quem abre não
tem conta no painel. O que autoriza é o código do convite e o token do
cadastro, conferidos dentro de cada rota/action com `service_role`; a anon key
nunca chega perto dessas tabelas, que por isso não têm policy para `anon`.

Tabelas: `convites`, `termos_indicacao`, `cedentes`, `aceites_termo`,
`cedente_contas` (`20260819180000_cedentes_convites.sql`),
`cedente_credenciais` (`20260819200000_credenciais_e_termo.sql`) e o rastro
de envio por conta em `cedente_contas` (`20260820010000_milhasflow_por_conta.sql`).

### As credenciais

Login e senha de cada programa são o motivo de o cadastro guiado existir — sem
eles a agência não opera a conta que o titular criou. Ficam **cifrados**
(AES-256-GCM, `web/lib/cripto.ts`) com uma chave que só vive na env do
servidor: quem tirar um dump do banco não lê senha nenhuma.

Ficam também numa **tabela própria**, não como coluna de `cedente_contas`, por
um limite do Postgres: RLS é por linha, não por coluna. Se a senha morasse
junto do progresso, a policy que deixa todo colaborador ver o andamento das
contas entregaria a senha junto. `cedente_credenciais` não tem GRANT para
`authenticated` nenhum — só `service_role`, e só depois de `exigirAdmin()` na
Server Action que decifra.

Sem `CREDENCIAIS_CHAVE` configurada, o passo a passo **recusa** a senha em vez
de gravar em claro.

### Diferença deliberada em relação ao trademiles

**Termo versionado e congelado.** Editar o texto de uma versão já assinada
mudaria, retroativamente, o que alguém concordou — então publicar texto novo
cria versão nova, e o aceite guarda versão, IP e user-agent. O termo da LF
(`v1-2026-08`) já vai na migration, para qualquer ambiente novo nascer com o
link de convite funcionando.

### O envio pro MilhasFlow

O MilhasFlow não expõe `/rest/v1/` (schema OpenAPI desligado no projeto —
`401` mesmo autenticado), então o formato foi descoberto na prática em
20/08/2026, testando nomes de tabela candidatos direto pelo PostgREST com
login de verdade (`scripts/descobrir_tabelas_milhasflow.py` ajuda a repetir
esse processo se algo mudar de novo).

A tabela é `miles_accounts`, e tem **uma linha por conta de programa**, não
uma por cedente — quem tem LATAM Pass + Smiles + Livelo vira três linhas lá,
cada uma repetindo nome/CPF/e-mail/nascimento e com `program`/`username`/
`password` próprios (nomes de programa confirmados: `LATAM Pass`, `Smiles`,
`Livelo`, `Esfera`). Por isso `web/lib/milhasflow.ts` envia por conta, e o
rastro de "já subiu" (`milhasflow_id`, `milhasflow_enviado_em`,
`milhasflow_erro`) fica em `cedente_contas`, não em `cedentes` — a ficha do
cedente mostra o status de cada conta separado, com reenvio independente.

Aprovar dispara o envio de toda conta com status "criada" que ainda não
subiu; sem `MILHASFLOW_EMAIL`/`SENHA`/`ANON_KEY` configurados, aprovar segue
funcionando normal e as contas ficam marcadas como não enviadas.

O clube de fidelidade (assinatura mensal, aba "Clube" no MilhasFlow) é um
campo à parte de `status` — `club_active`, visto num payload real junto de
`club_due_day`, `club_monthly_cost`, `club_points_monthly` e
`club_reminder_enabled`. O default do MilhasFlow pra ele é `true`, então o
envio manda `club_active: false` explícito: a adesão ao clube é uma etapa
posterior e manual, feita quando o cedente de fato assina.

### Pendente

- **O roteiro de cada aba** (`ROTEIRO` em `app/cedente/[token]/PassoAPasso.tsx`)
  espera o conteúdo do PDF de instruções. Sem ele a aba mostra o formulário e
  um aviso no lugar do passo a passo.

---

## O que ainda limita

Nenhum é problema de código:

1. **PDF por emissão** — a LATAM depende dele. Hoje o índice cobre os 16
   localizadores ativos, mas PDF novo só entra depois de `indexar_links.py`
2. **Dados faltando no CRM** — voos sem passageiro, `CRM-XXXXX` no lugar do PNR,
   registros sem companhia. Lista em `pendencias_*.csv`
3. **`TSTAAX` / `AD 2660` com rota errada no MilhasFlow** — o cadastro diz que
   sai de CNF; malha e portal da Azul dizem **VCP**, e o trecho anterior chega
   em VCP. Enquanto não for corrigido, o alerta reaparece a cada rodada
4. **GOL depende do humor do reCAPTCHA** — em 30/07 passaram 6 de 8 sem
   nenhuma barrada, bem melhor que os 4 de 8 de 29/07. O que não passa vai ao
   painel, então a cobertura não se perde — mas a taxa varia por sessão.
   Desde 31/07/2026 o resumo diário avisa quantas reservas estão paradas lá
   e qual embarca primeiro, em vez de depender do operador lembrar de abrir
   o painel (ver **Link pronto e aba Urgente**)
