-- Segunda versão do termo de ciência e autorização: adiciona a cláusula
-- proibindo o TITULAR de usar os pontos/milhas das contas (Livelo, Stix,
-- Dotz) como forma de pagamento em farmácias, postos de combustível e
-- estabelecimentos parecidos.
--
-- Motivo: farmácias como Droga Raia/Drogasil e postos Shell aceitam pontos
-- Livelo (via parceria com a Stix) como desconto na compra, bastando
-- informar o CPF no caixa — sem senha nem confirmação extra. Pontos Livelo
-- também podem ser transferidos pro Dotz e gastos do mesmo jeito em outras
-- redes. Se o TITULAR gastar o saldo assim, ele deixa de existir pra ser
-- transferido/vendido pela LF Viagens — prejuízo direto na operação.
--
-- Versão nunca é reescrita (ver comentário em
-- web/app/(painel)/cedentes/termos/actions.ts): quem já aceitou a v1
-- continua com o texto que aceitou. Esta migration publica a v2 como a
-- versão ativa pra novos convites e desativa a v1.

update termos_indicacao set ativo = false where versao = 'v1-2026-08';

insert into termos_indicacao (titulo, slug, versao, corpo, ordem, ativo)
select
    'Termo de ciência e autorização',
    'termo-ciencia-autorizacao-v2',
    'v2-2026-08',
    $termo$TERMO DE CIÊNCIA E AUTORIZAÇÃO – LF Viagens

Este termo tem por finalidade registrar a ciência expressa e autorização do TITULAR da conta para participação nas operações de compra e venda de milhas realizadas pela LF VIAGENS LTDA, inscrita no CNPJ sob nº 61.337.998/0001-09.

1. OBJETO E FUNCIONAMENTO DAS OPERAÇÕES
A LF Viagens atua na intermediação de passagens aéreas emitidas por meio dos programas de fidelidade Livelo, LATAM Pass e Smiles.
Para viabilizar operações com margem de lucro, podem ser necessárias as seguintes etapas:
• Adesão a clubes de pontos/milhas (Livelo, LATAM Pass e Smiles);
• Aquisição de pontos e milhas com recursos próprios da LF Viagens;
• Transferências internas de pontos;
• Emissão de passagens aéreas;
• Comercialização dessas passagens em balcões especializados de milhas.

2. DO INVESTIMENTO E AUSÊNCIA DE PREJUÍZO AO CEDENTE
Todo o capital investido nas operações é exclusivamente da LF Viagens. O TITULAR declara ciência de que:
• Não realiza qualquer pagamento, PIX, transferência ou investimento;
• Não assume risco financeiro;
• Não sofre prejuízo patrimonial;
• Não possui responsabilidade por atrasos, cancelamentos ou falhas operacionais.

3. DO PAGAMENTO AO TITULAR
Os valores pagos ao TITULAR correspondem à antecipação de lucro pela utilização da conta nos programas de fidelidade.
O pagamento:
• Será realizado exclusivamente ao TITULAR da conta;
• Será feito via PIX em conta bancária de mesma titularidade;
• Não será realizado pagamento em conta de terceiros.

4. DA AQUISIÇÃO DE PONTOS
O TITULAR declara ciência de que a aquisição de pontos e milhas realizada pela LF Viagens não gera qualquer dívida, obrigação financeira ou responsabilidade tributária ao TITULAR.

5. DAS VALIDAÇÕES DE IDENTIDADE E DOCUMENTAÇÃO
O TITULAR declara ciência de que as plataformas Livelo, LATAM Pass e Smiles poderão, a qualquer tempo, solicitar validações adicionais de identidade, conforme suas políticas internas, incluindo, sem se limitar a:
• Documento oficial de identificação com foto (RG ou CNH) emitido há menos de 10 (dez) anos;
• Comprovante de residência atualizado;
• Selfie para conferência facial;
• Biometria facial;
• Envio de códigos por SMS;
• Confirmações por ligação telefônica ou aplicativos oficiais.
O TITULAR compromete-se a fornecer tais validações sempre que solicitado, de forma tempestiva e verdadeira, ciente de que a negativa, omissão ou recusa poderá resultar em bloqueio ou suspensão da conta junto às plataformas.
No caso específico da LATAM, o TITULAR declara ciência de que a biometria facial poderá ser obrigatória para viabilizar a venda e emissão de passagens com os pontos da conta. Nessa hipótese, o titular recebera 10$ reais por biometria facial necessária para conclusão das operações vinculadas àquela venda.
O TITULAR declara ainda ciência de que a recusa, omissão, atraso injustificado ou não realização das biometrias faciais solicitadas pela LATAM autoriza o cancelamento imediato deste vínculo/termo, uma vez que tal conduta gera prejuízo operacional e financeiro direto à LF Viagens.

6. DA PROIBIÇÃO DE USAR OS PONTOS COMO FORMA DE PAGAMENTO
O TITULAR declara ciência de que diversos estabelecimentos — como farmácias (ex.: Droga Raia, Drogasil) e postos de combustível (ex.: postos Shell) — aceitam pontos Livelo, Stix ou Dotz como forma de pagamento (total ou parcial) de compras, bastando informar o CPF no caixa ou usar o aplicativo do estabelecimento, sem necessidade de senha ou autorização adicional do TITULAR.
Como os pontos e o saldo das contas vinculadas a este termo pertencem à operação da LF Viagens e se destinam exclusivamente à transferência, aquisição de passagens e revenda, o TITULAR declara ciência de que:
• É PROIBIDO usar, resgatar, transferir ou gastar pontos Livelo, Stix, Dotz ou qualquer saldo equivalente das contas vinculadas a este termo para pagar, total ou parcialmente, compras em farmácias, postos de combustível, mercados, aplicativos ou qualquer outro estabelecimento que os aceite como forma de pagamento;
• Essa proibição vale mesmo quando o pagamento com pontos é oferecido como opção pelo próprio estabelecimento ou aplicativo, no caixa ou no ato da compra, e independe de o TITULAR ter sido quem iniciou a compra;
• O uso indevido dos pontos para esse fim reduz ou zera o saldo que seria utilizado pela LF Viagens, gerando prejuízo financeiro direto à operação.
O descumprimento desta cláusula é considerado falta grave para os fins deste termo, sujeitando o TITULAR às mesmas consequências previstas para a negativa de validação de identidade (bloqueio ou suspensão da conta, cancelamento do vínculo/termo e responsabilização pelo prejuízo financeiro causado à LF Viagens).

7. DA PROTEÇÃO E TRATAMENTO DE DADOS
Os dados pessoais fornecidos pelo TITULAR serão armazenados em ambiente seguro, em banco de dados protegido (OneDrive corporativo da LF Viagens).
O TITULAR poderá solicitar, a qualquer momento, a exclusão definitiva e irrevogável de seus dados. Ciente, contudo, de que:
• A exclusão inviabiliza novo ingresso;
• Não será permitida nova indicação;
• O vínculo operacional será encerrado permanentemente.

8. DA INDICAÇÃO DE NOVOS CEDENTES
Para unificação de novos cedentes, poderá ser pago o valor de R$ 20,00 (vinte reais) por indicação válida.
Caso o cedente indicado descumpra o presente termo e gere prejuízo à LF Viagens, o TITULAR que realizou a indicação ficará impossibilitado de realizar novas indicações.

9. DA RESCISÃO E DAS CONSEQUÊNCIAS DA NEGATIVA DE VALIDAÇÃO
Este termo poderá ser rescindido a qualquer momento por qualquer das partes.
Caso o TITULAR opte por não prosseguir com as operações, a LF Viagens poderá apenas consumir os pontos e milhas já adquiridos, a fim de evitar prejuízo financeiro.
A negativa injustificada, omissão ou recusa no fornecimento das validações descritas neste termo, bem como o uso dos pontos como forma de pagamento em desacordo com o item 6, poderá resultar em:
• Bloqueio ou suspensão da conta do TITULAR;
• Cancelamento de operações em andamento;
• Prejuízo financeiro direto à LF Viagens.

Nessas hipóteses, o TITULAR declara ciência de que seus dados poderão ser removidos do banco de dados e ficará impedido de futuras negociações.

10. DO IMPOSTO DE RENDA
Os valores eventualmente recebidos pelo TITULAR possuem caráter eventual, não configurando vínculo empregatício.
Cabe ao TITULAR avaliar eventual obrigação de declaração à Receita Federal.

11. DA VERACIDADE E CIÊNCIA EXPRESSA
Para fins de verificação pública e transparência, o TITULAR poderá consultar o perfil oficial da empresa no Instagram: @LF.VIAGENS.
Ao manifestar concordância, o TITULAR declara que:
• Leu integralmente este termo;
• Compreendeu seu funcionamento;
• Não sofreu indução, erro ou coação;
• Autoriza expressamente a utilização de sua conta conforme descrito.$termo$,
    0,
    true
where not exists (select 1 from termos_indicacao where versao = 'v2-2026-08');
