# Catálogo de limitações do protótipo

Atualizado em **14/11/2026**. Contrato de saída **schema 0.4**.

Este é o registro vivo das restrições identificadas durante a leitura do código.
Ele reúne limites técnicos, escolhas de escopo e integrações previstas. A
presença de um item aqui **não significa que ele deva ser corrigido
agora**: há limites técnicos, escolhas de escopo, integrações futuras e decisões
explicitamente adiadas.

**Limitação do analisador não é necessariamente problema da pipeline.**
True, False e None são resultados do modelo; não são observações do runner.

## Como usar este catálogo

Cada item tem um identificador estável, uma explicação do limite, uma consequência
prática e uma referência por arquivo e função. Procure pelo identificador quando
uma limitação voltar à conversa.

Comece por:
- **LIM-001:** relações por nome individual de artefato.
- **LIM-002 e LIM-033:** relações invisíveis e sugestões de paralelismo.
- **LIM-013 a LIM-019:** contexto e avaliação de condições.
- **LIM-020 a LIM-024:** estruturas não modeladas.
- **LIM-030:** acompanhamento de achados deliberadamente adiado.
- **LIM-039:** o que os testes atuais ainda não demonstram.
- **LIM-041:** acesso a outputs e resultados exige dependência direta.

Use `coverage` para consultar o alcance de cada análise, `limitations` para
ler restrições detectadas e `assumptions` para conhecer as premissas gerais.
O catálogo inclui também limites que o programa ainda não sinaliza.

Fontes locais do registro:
- [model.py](../src/pipeline_impact/model.py): leitura, normalização e grafo.
- [conditions.py](../src/pipeline_impact/conditions.py): expressões e estados.
- [analyzer.py](../src/pipeline_impact/analyzer.py): artefatos, regras e comparação.
- [cli.py](../src/pipeline_impact/cli.py): entrada e códigos de saída.
- [Próximos passos](PROXIMOS-PASSOS.md): requisitos ainda não implementados.

## 1. Artefatos e relações de dados

### LIM-001 — Relações por nome individual

**Tipo:** recorte atual da análise de artefatos.

Reconhecemos o vínculo entre uploads e downloads por igualdade do nome literal do
artefato. Um upload e um download chamados app podem formar uma relação no modelo.

Não representamos um download sem name como consumo automático de todos os
artefatos. No upload, a ausência de name usa o padrão artifact; no download, fica
None e gera uma limitação no próximo bloco.

**Impacto:** uma pipeline válida que baixa todos os artefatos pode ficar fora da
análise dessa transferência. Isso não prova que seu download esteja errado.

**Referência:** analyzer.py, artifact_steps() e agrupamento por name em snapshot().

### LIM-002 — Somente duas actions são reconhecidas

**Tipo:** reconhecimento limitado, com fronteira registrada na cobertura.

O levantamento reconhece actions/upload-artifact e actions/download-artifact.
Actions personalizadas, actions compostas e comandos run podem realizar operações
de transferência que não interpretamos.

O reconhecimento registra actions fora do seu escopo em `coverage`. O corpo
dessas actions e os comandos `run` permanecem fora da interpretação de
transferências. Consulte o escopo registrado mesmo quando `limitations` estiver
vazio.

**Impacto:** com upload personalizado e download oficial, podemos apontar ausência
de produtor reconhecido mesmo quando a transferência real está organizada. Com
ambos personalizados, a relação inteira pode ficar invisível. Isso também afeta
as sugestões de paralelismo; veja LIM-033.

**Referência:** analyzer.py, artifact_steps(), filtro de supported_actions.

### LIM-003 — Nomes dinâmicos de artefatos

**Tipo:** recurso não interpretado, com sinalização.

Nas duas actions reconhecidas e em jobs não descartados por unresolved_job(),
um nome contendo uma expressão, como app-${{ matrix.os }}, não é resolvido para
seus possíveis valores. O step é excluído do levantamento e recebe uma mensagem
de seletor dinâmico, múltiplo ou externo. Outras actions podem ser ignoradas antes
dessa verificação, conforme LIM-002.

**Impacto:** não sabemos quais produtores e consumidores compartilham o mesmo
nome em cada execução. Não devemos substituir isso por uma conclusão de ausência
real do artefato.

**Referência:** analyzer.py, artifact_steps(), verificação de "${{" em name.

### LIM-004 — Padrões e seleção múltipla

**Tipo:** recurso não interpretado, com sinalização.

Nas duas actions reconhecidas e em jobs não descartados, a presença do parâmetro
pattern faz o seletor ser considerado não suportado.
Não expandimos padrões para descobrir todos os artefatos selecionados nem
modelamos todas as opções de agregação da action.

Downloads por `artifact-ids` também ficam fora do modelo. Um download somente
por ID é registrado como seletor fora do escopo porque falta o nome literal.
[Opções da action de download](https://github.com/actions/download-artifact#inputs).

**Impacto:** uma relação que usa um padrão de nomes não é representada como várias
relações individuais. Não equivale a erro no padrão configurado.

**Referência:** analyzer.py, artifact_steps(), selector_keys.

### LIM-005 — Outras execuções e repositórios

**Tipo:** recorte local da análise.

Nas duas actions reconhecidas e em jobs não descartados, a presença de run-id,
repository ou github-token gera limitação e exclui o step do levantamento. A
regra verifica a presença da chave, sem determinar se um caso específico poderia
ser resolvido.

**Impacto:** não procuramos produtores em outra execução ou repositório, nem
comprovamos a existência de artefatos externos. Um produtor externo pode estar
correto e simplesmente fora do modelo local.

**Referência:** analyzer.py, artifact_steps(), selector_keys.

### LIM-006 — Ativação não comprova arquivo disponível

**Tipo:** fronteira da análise estática.

Não executamos o comando que deveria gerar o arquivo, não verificamos o conteúdo
de path, não abrimos o artefato e não confirmamos sucesso efetivo do upload.

**Impacto:** um upload True significa etapa ativa no cenário modelado. Ele pode,
na execução real, não encontrar arquivos ou falhar. A ausência de alerta não
prova disponibilidade ou integridade do pacote.

**Referência:** model.py, load()/parse(); analyzer.py, artifact_steps() e assumptions.

### LIM-007 — Múltiplos produtores simplificados

**Tipo:** aproximação do modelo.

Agrupamos uploads pelo mesmo nome. Na análise contextual, um produtor reconhecido
ativo com precedência garantida sobre o consumidor impede o alerta de que todos
os produtores anteriores foram pulados.

Não verificamos conflitos entre uploads, conteúdos diferentes, restrições de
imutabilidade, sobrescrita ou regras particulares das versões das actions.

**Impacto:** encontrar um produtor ativo não comprova que o consumidor receberá o
conteúdo pretendido nem que todos os uploads da execução serão aceitos.

**Referência:** analyzer.py, snapshot(), producers e producer_states.

### LIM-008 — A referência da action não é interpretada

**Tipo:** normalização com perda de detalhe.

O texto depois de @ é descartado para reconhecer o nome da action. Não validamos
se a versão ou revisão existe, nem suas diferenças de comportamento.

Também não validamos todos os parâmetros aceitos por cada versão.

Por exemplo, em referências que aceitam `archive: false`, a action de upload
usa o nome do arquivo. O analisador ainda forma a relação pelo `name` do YAML
ou pelo padrão `artifact`, o que pode produzir uma relação incorreta sem
sinalizar essa opção em `coverage`.
[Opções da action de upload](https://github.com/actions/upload-artifact#inputs).

**Impacto:** reconhecer upload-artifact@v4 e outra referência pelo mesmo nome não
comprova que o modelo seja fiel a todos os comportamentos dessas referências.

**Referência:** analyzer.py, artifact_steps(), uses.split("@").

### LIM-009 — Referências ao contexto needs reconhecidas parcialmente

**Tipo:** reconhecimento parcial de relações de dados.

O analisador reconhece referências literais como `needs.build.outputs.version`
e `needs.build.result` dentro de expressões nos valores do workflow. Em
`if` de jobs e steps, a leitura também considera a forma sem delimitadores.
Colchetes com chaves textuais literais podem ser combinados com pontos,
por exemplo em `needs['build'].outputs['version']`. A R06 verifica a
presença da dependência direta para esses acessos reconhecidos.
Consulte LIM-041.

O reconhecimento deixa de fora referências dinâmicas e filtros por coringa.
Os pares em `data_relations` identificam somente produtor e consumidor.
O modelo deixa em aberto a existência de um output, seu valor e o resultado
real do produtor. A disponibilidade do contexto em cada campo da sintaxe
do GitHub Actions também fica fora da verificação.

**Impacto:** expressões fora do subconjunto podem deixar relações
invisíveis. Uma dependência direta confirmada pela R06 indica acesso
estrutural no modelo, com a execução e os valores ainda indeterminados.

**Referência:** `job_needs_references()` em `needs_references.py` e
`check_direct_needs()` em `analyzer.py`.

### LIM-010 — Ordem estrutural não equivale a consumo ativo

**Tipo:** alcance de uma regra específica.

R02 procura downloads sem upload reconhecido com precedência garantida no modelo.
Essa regra não usa a tabela de estados por contexto. Ela exclui diretamente
consumidores cujo if do job ou do próprio step, depois de normalizado, seja
exatamente o texto false.

Outras expressões que desativem o consumidor podem continuar recebendo esse
diagnóstico estrutural.

**Impacto:** o achado deve ser interpretado como evidência sobre a estrutura, não
como prova de falha em uma execução ativa. Um produtor invisível também pode
explicar o alerta, como em LIM-002.

**Referência:** analyzer.py, snapshot(), guardas de R02_ARTIFACT_ORDER.

## 2. Expressões, contextos e estados

### LIM-011 — Linguagem de condições parcial

**Tipo:** subconjunto de interpretação.

Reconhecemos strings entre aspas simples, booleanos, igualdade/diferença, negação,
E, OU, parênteses e quatro funções de status. Não interpretamos toda a linguagem
de expressões do GitHub Actions.

Funções como contains(), comparações numéricas, acesso com colchetes e outras
construções ficam fora do suporte atual. O padrão lexical também restringe os
nomes que podem ser reconhecidos.

**Impacto:** uma expressão válida pode gerar UnsupportedCondition. Isso não
demonstra um defeito na configuração.

**Referência:** conditions.py, padrões de token, atom() e comparison().

### LIM-012 — Tipos e valores indeterminados

**Tipo:** regras de avaliação deliberadamente restritas.

O interpretador aceita texto, booleano e `None`. O arquivo passado em
`--contexts` admite apenas chaves de evento conhecidas, com valores textuais
ou `null` nos campos opcionais. O interpretador preserva os tipos durante a
comparação.

Um identificador ausente gera UnsupportedCondition. Um identificador presente
com None pode propagar indeterminação em operações lógicas, mas comparações com
None também são rejeitadas.

**Impacto:** não existe raciocínio simbólico geral. Ausência e indeterminação
explícita não percorrem necessariamente o mesmo caminho.

**Referência:** conditions.py, atom(), comparison() e tratamento em states().

### LIM-013 — Cobertura restrita aos contextos informados

**Tipo:** limitação de cobertura contextual.

O analisador avalia somente os contextos informados. O arquivo de teste
`cases/contexts.json` fornece três cenários sintéticos. A CLI suspende a R03
quando o arquivo de contextos é omitido ou contém uma lista vazia.

**Impacto** As conclusões de cada análise condicional valem para os contextos
avaliados. Outras branches, tags, inputs ou eventos podem levar a outros estados.

**Referência** `snapshot()` em `analyzer.py` e `cases/contexts.json`.

### LIM-014 — Contexto de evento parcial e dependente da origem

**Tipo** Escopo do contexto e validade da interpretação.

Na CLI, os valores vêm do arquivo fornecido. Na integração com Actions,
`read_github_event()` extrai o nome do evento, sua referência e, quando
disponíveis, as referências de origem e destino do PR. O contexto mantém um
conjunto de chaves planas de evento.

Os valores automáticos descrevem o PR do repositório que hospeda o analisador.
Quando o YAML veio de outro repositório ou foi projetado para outra branch,
os valores do PR representam um cenário diferente daquele ambiente de origem.
Um contexto local explícito pode representar as referências da origem.

**Impacto** Informações externas ao conjunto coletado, como valores produzidos
por jobs, podem ficar indeterminadas. Um evento real fornece dados de entrada
para uma execução hipotética.

**Referência** `atom()` em `conditions.py`, `load_contexts()` em
`event_context.py` e `read_github_event()` em `scripts/audit_pull_request.py`.

### LIM-015 — Subconjunto de eventos e filtros

**Tipo** Elegibilidade parcial dos contextos.

O modelo admite eventos declarados sem filtros e, para `push` e
`pull_request`, um único filtro literal de `branches` ou `branches-ignore`.
Para push, a branch vem de `github.ref`. Para pull request, é a branch de
destino em `github.base_ref`. A elegibilidade pode ficar indeterminada quando
falta a referência necessária ou quando o gatilho usa padrões, filtros de
caminhos ou tags, combinações, agendamentos, inputs ou variantes com
parâmetros fora desse subconjunto.

**Impacto** A indeterminação é registrada por contexto. Se houver pelo menos
um contexto elegível e outro indeterminado, a cobertura contextual é parcial.
Se nenhum for elegível e houver indeterminação, a R03 fica suspensa. Se todos
forem excluídos pelos gatilhos, a regra é não aplicável.

**Referência** `event_eligibility()` em `event_context.py` e `snapshot()` em
`analyzer.py`.

### LIM-016 — Sucesso, falha e cancelamento simplificados

**Tipo:** premissa do cenário modelado.

failure() e cancelled() retornam False. success() devolve o parâmetro success;
always() devolve True. Não consultamos logs ou resultados reais dos comandos.

`continue-on-error` pode ter sua alteração reportada no job ou no step.
Quando o valor booleano muda em um step identificado, o Markdown descreve
uma consequência possível caso a etapa falhe. Os estados calculados para
condições mantêm a premissa de sucesso.

**Impacto:** não cobrimos todos os caminhos de exceção, falha ou cancelamento do
runner. success=False não é sinônimo de falha real de um comando.

**Referência:** conditions.py, atom()/states(); analyzer.py, compare().

### LIM-017 — Resultados anteriores dos steps não acumulados

**Tipo:** aproximação da execução dentro do job.

Cada if de step é avaliado usando o padrão success=True. Não acumulamos falhas,
cancelamentos ou efeitos dos steps anteriores. Depois combinamos o resultado
com active, o estado do job.

Um step pulado não transforma o job inteiro em desativado no modelo.

**Impacto:** estados calculados não reproduzem todas as transições internas de
um job real, especialmente depois de erros.

**Referência:** conditions.py, states(), evaluate(step["if"], context).

### LIM-018 — Regra sobre todos os ancestrais

**Tipo:** aproximação que precisa ser confrontada com o runner.

O cálculo de success considera todos os ancestrais, inclusive indiretos.
Um ancestral False pode bloquear um descendente mesmo quando há, no caminho,
um job intermediário True por always().

**Exemplo:** em build -> deploy -> notify -> audit, deploy=False e notify=True
não bastam para deixar audit sem if ativo no código atual.

**Impacto:** não devemos assumir equivalência completa entre essa regra e o
comportamento real do GitHub Actions.

**Referência:** conditions.py, states(), ancestor_states.

### LIM-019 — Sem curto-circuito completo

**Tipo:** restrição do interpretador atual.

A direita de && e || é interpretada antes de tri_and()/tri_or() combinar os
resultados. Portanto, true || inputs.publish gera exceção se inputs.publish
estiver ausente, apesar do true à esquerda.

Se o identificador estiver presente com None, tri_or(True, None) pode produzir
True. A lógica de três valores não elimina a restrição da leitura da direita.

**Impacto:** algumas expressões que poderiam ter um resultado conhecido ficam
indeterminadas pela falta de informação em outra parte.

**Referência:** conditions.py, conjunction() e disjunction().

## 3. Estruturas do workflow e grafos

### LIM-020 — Matrizes e strategy não expandidos

**Tipo:** estrutura não modelada.

Mantemos um único nó por job. Não criamos uma execução para cada combinação de
matriz. Basta a chave strategy existir para unresolved_job() sinalizar limitação.

states() substitui inclusive um active=False por None quando o job é não resolvido.

**Impacto:** condições, relações e paralelismo entre instâncias da matriz não são
representados. A guarda pode descartar uma conclusão já conhecida.

**Referência:** model.py, parse()/unresolved_job(); conditions.py, states().

### LIM-021 — Workflows reutilizáveis não expandidos

**Tipo:** estrutura não modelada.

uses no nível do job marca uma chamada que não expandimos. Não buscamos o arquivo
chamado, seus jobs internos ou sua cadeia de dependências.

uses dentro de um step comum não é essa mesma guarda; actions personalizadas
nessa posição têm o problema de cobertura descrito em LIM-002.

**Impacto:** transferências e condições internas do workflow chamado podem ficar
fora da representação.

**Referência:** model.py, Workflow.unresolved_job() e parse().

### LIM-022 — Paralelismo entre steps fora do escopo inicial

**Tipo:** recorte aprovado, registrado como FUT-01.

Não modelamos a concorrência e a sincronização associadas a parallel, background,
wait, wait-all e cancel. Começamos pelo paralelismo entre jobs.

Não podemos assumir que a posição textual de um step concorrente representa a
ordem de término das operações.

**Impacto:** o job é considerado não resolvido; sua participação nas análises
fica limitada. Essas chaves não são declaradas inválidas por causa disso.

**Referência:** model.py, parse()/unresolved_job(); próximos passos, paralelismo
entre steps fora da integração inicial.

### LIM-023 — Guardas baseadas na presença da chave

**Tipo:** conservadorismo da implementação.

As chaves de concorrência entre steps são verificadas por presença, sem avaliar
seu valor. Por exemplo, background: false ainda aciona a limitação.

A presença de strategy também basta, sem analisar em detalhe seu conteúdo.

**Impacto:** podemos limitar a análise em uma configuração que admitiria um
tratamento mais preciso. Refinar essa guarda é diferente de implementar toda a
concorrência entre steps.

**Referência:** model.py, parse() e Workflow.unresolved_job().

### LIM-024 — Grupos concurrency não interpretados

**Tipo:** suspensão ampla de sugestões.

Não modelamos grupos, filas ou cancelamentos de concurrency. Sua presença na
raiz ou em qualquer job suspende globalmente as sugestões de paralelismo.

**Impacto:** a suspensão pode ser mais ampla que a restrição real, que talvez
afete apenas um job ou grupo. Isso não significa erro na pipeline.

**Referência:** model.py, parse(); analyzer.py, has_concurrency em snapshot().

### LIM-025 — Validação parcial da configuração

**Tipo:** fronteira do carregador.

parse() verifica estrutura, alguns tipos, identificadores, dependências e ciclos.
Não valida integralmente todos os campos, parâmetros, expressões e combinações
permitidos pelo GitHub Actions.

Os arquivos precisam usar UTF-8. Na leitura, valores YAML incompatíveis com o
modelo JSON são rejeitados com erro de entrada, incluindo datas convertidas em
objetos Python, dados binários, conjuntos, números não finitos e referências
recursivas. Uma data entre aspas permanece um texto suportado. Essa fronteira
evita que valores não representáveis provoquem um traceback durante a análise;
ela não constitui uma validação completa do formato de workflows.

Uma configuração inválida para o GitHub pode passar pela leitura. Por exemplo,
um job comum com `steps: []` e sem `runs-on` passa por essas validações.
Pela leitura de `compare()`, uma chave numérica entre campos extras de um job
pode chegar à ordenação junto de uma chave textual como `runs-on`. A ordenação
pode levantar `TypeError` fora do tratamento de erros da CLI.

**Impacto:** ser aceito pelo nosso parser não certifica validade completa no
GitHub. Rejeitar algo fora do suporte também não prova que o GitHub o rejeitaria.

**Referência:** model.py, WorkflowLoader, unique_mapping(), parse() e load();
tests/test_model.py e tests/test_cli.py.

### LIM-026 — Grafo não é cronograma observado

**Tipo:** limite de interpretação dos resultados.

As arestas representam needs. A ordem topológica é uma ordem válida para
processar o modelo. Ela não contém duração, capacidade de runners, filas ou
sobreposição temporal observada.

descendants() devolve uma lista alfabética; essa ordem não é ordem de execução.

**Impacto:** pares sem precedência não comprovam paralelismo real nem economia.

**Referência:** model.py, edges/ancestors()/descendants()/parse(); analyzer.py,
structurally_unordered_pairs.

### LIM-027 — Campo armazenado não significa efeito interpretado

**Tipo:** cobertura comportamental parcial.

Podemos preservar um campo e detectar sua alteração sem interpretar seu efeito.
UNMODELED_JOB_CHANGE e UNMODELED_WORKFLOW_CHANGE tornam isso explícito.

A comparação deixa de fora os rótulos `name` e `run-name` na raiz e
`name` no job. Uma alteração restrita a esses rótulos pode deixar
`changes` vazio.

**Impacto:** detectar, por exemplo, que um campo de configuração mudou não
significa prever todas as consequências sobre a execução.

**Referência:** analyzer.py, compare(), campos acompanhados e UNMODELED_*_CHANGE.

## 4. Comparação e recomendações

### LIM-028 — Renomeação de job é remoção e adição

**Tipo:** correspondência estrutural limitada.

A comparação usa as chaves dos jobs. Não reconhecemos automaticamente que um job
renomeado é a mesma entidade da versão anterior.

**Impacto:** uma renomeação pode aparecer como remoção/adição, e não como simples
mudança de nome. Isso independe do acompanhamento de achados que foi adiado.

**Referência:** analyzer.py, compare(), união dos identificadores de jobs.

### LIM-029 — Granularidade dos steps e localização

**Tipo:** precisão de comparação e apresentação.

`STEP_CHANGE` registra a mudança da lista por job. `step_changes` detalha as
etapas de jobs presentes nas duas versões, com pareamento por identidade
reconhecível. IDs duplicados e outros casos sem correspondência única podem
aparecer como `unmatched`. Mudanças simultâneas de nome e de conteúdo podem
impedir a identificação do mesmo step. A ordem relativa é verificada entre
pares reconhecidos em jobs sequenciais suportados.

O pareamento por nome tem prioridade sobre a comparação do conteúdo. Ao
renomear um step e reutilizar seu nome em outro step na mesma mudança, o
modelo pode associar a etapa ao nome reutilizado. IDs únicos e estáveis têm
prioridade e permitem distinguir essas etapas.

Em `fields`, o relatório registra os valores comparados de `name`, `if`,
`continue-on-error` e `uses` literal quando suportados. Campos como `run`,
`env` e `with` são indicados pelo nome em `other_fields` quando mudam.
Nomes e condições exibidos no relatório devem ser tratados como conteúdo da
configuração.

`location` identifica o job consumidor e a posição do step na lista, a partir
de 1. A segunda etapa corresponde ao índice Python 1. Em R05, `location`
identifica o job dependente e seu campo `needs`.

**Impacto** A localização identifica uma posição no YAML analisado. A
correspondência é delimitada ao job e ao par de arquivos em análise. A
rastreabilidade de steps ou de achados ao longo do histórico está fora desse
pareamento.

`context_comparisons` é gerado quando muda o `if` de um step pareado. Se apenas
o `if` do job ou o gatilho mudar, os estados podem diferir entre
`before.context_evaluations` e `after.context_evaluations` sem um registro
individual em `step_changes`. A ordem relativa também deixa de fora
dependências gerais entre steps, como uma referência a `steps.setup.outputs`.

**Referência** `compare_job_steps()` em `step_comparison.py` e `compare()` em
`analyzer.py`.

### LIM-030 — Acompanhamento de achados adiado

**Tipo:** decisão de escopo, não defeito a corrigir automaticamente.

O schema 0.4 apresenta os achados atuais. A classificação em novos,
preexistentes ou resolvidos permanece adiada.

O hash de `finding()` usa evidências que podem mudar com a posição. Os campos
`location` e `coverage` ficam fora do cálculo. O ID serve como referência
técnica do achado na configuração analisada.

**Impacto:** o mesmo problema pode ser apontado novamente. Não informamos que uma
ocorrência histórica persistiu ou foi resolvida. Essa capacidade foi adiada
explicitamente, em vez de manter uma classificação imprecisa.

**Referência:** analyzer.py, finding()/compare(); decisão de 27/10/2026.

### LIM-031 — Impacto estrutural não é causalidade observada

**Tipo:** limite das conclusões.

Na comparação, `changes` descreve diferenças da configuração, `affected_jobs`
reúne descendentes potencialmente afetados e `after.findings` traz o diagnóstico
atual. A auditoria apresenta `analysis.findings` para o arquivo fornecido.

**Impacto:** não podemos dizer que cada alerta atual foi causado pela alteração,
nem que todo descendente teve seu comportamento efetivamente prejudicado.

**Referência:** analyzer.py, compare(), changes/affected_jobs/after.findings.

### LIM-032 — Revisão de uma aresta por vez

**Tipo:** alcance da recomendação de paralelismo.

R05 examina a remoção hipotética de uma dependência por vez. Não procura uma
refatoração global ótima nem simula novamente todos os comportamentos depois
dessa remoção.

Não reescreve o YAML e não estima economia de tempo.

**Impacto:** uma oportunidade é um ponto para investigação, não um plano completo
e validado de otimização.

**Referência:** analyzer.py, snapshot(), laço de R05_PARALLEL_REVIEW.

### LIM-033 — Ausência de relação reconhecida não prova independência

**Tipo:** risco central da recomendação.

Uma dependência pode proteger uma transferência invisível, um serviço externo,
um recurso compartilhado ou uma barreira contra falhas.

Já reproduzimos localmente que actions personalizadas não reconhecidas podem
deixar uma relação invisível e permitir uma sugestão de revisar a aresta.

**Impacto:** não tratar a sugestão como autorização automática para paralelizar.
A recomendação exige revisão e verificação experimental.

**Referência:** analyzer.py, data_pairs, breaks_data_relation e R05; LIM-002.

### LIM-034 — Guardas de paralelismo amplas e incompletas

**Tipo:** conservadorismo e cobertura parcial.

Job não resolvido, limitação de seletor de artefato ou `concurrency` suspendem
as sugestões. A cobertura de R05 registra os motivos da suspensão. Actions
fora do reconhecimento aparecem como fronteira em `coverage` e, sozinhas,
permitem que a verificação estrutural prossiga.

Limitações de condições também não entram diretamente em can_review_parallelism.
Uma referência não textual em `uses` torna o reconhecimento de artefatos
parcial, mas essa observação, isoladamente, também permite que a R05 prossiga.

**Impacto:** as sugestões dependem das relações reconhecidas e das guardas
implementadas. Consulte `coverage` para verificar escopo, situação e motivos.

**Referência:** analyzer.py, snapshot(), can_review_parallelism.

## 5. Integração e avaliação

### LIM-035 — Entrada local e seleção de versões no piloto

**Tipo:** estágio da implementação.

A CLI recebe um arquivo local em `audit` e dois na comparação. O piloto usa o
Git para extrair o YAML do SHA do PR e entrega uma cópia local à CLI. A seleção
automática de duas versões para comparação e um serviço HTTP são extensões
futuras.

No PR, o YAML analisado vem do SHA do head e o contexto pode trazer uma
referência de merge. Se a base tiver alterações no mesmo arquivo, a cópia
analisada pode diferir do YAML resultante do merge que o GitHub considera
no evento padrão de `pull_request`.
[Branch de merge do pull request](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#how-the-merge-branch-affects-your-workflow).

**Impacto:** o usuário ou a integração deve fornecer o caminho da configuração
auditada e, para comparar, também o caminho da versão anterior.

**Referência:** cli.py, main(); model.py, load(); scripts/audit_pull_request.py.

### LIM-036 — Histórico e métricas reais não coletados

**Tipo:** integração e avaliação pendentes.

Não coletamos execuções, tentativas, durações e seus vínculos com revisões do
workflow. Não calculamos ganho temporal observado ou estimado.

Uma coleta futura precisará associar os dados às configurações corretas e não
garantirá reconstruir todos os valores usados na execução.

**Impacto:** os resultados atuais não demonstram redução real de duração nem
representam o comportamento histórico de um repositório.

**Referência:** analyzer.py, assumptions; próximos passos, coleta de histórico.

### LIM-037 — Escopo do disparo condicional e da integração

**Tipo:** escopo do piloto e requisitos de integração planejados.

A CLI analisa os arquivos que recebeu. No piloto, um script verifica o diff
completo do PR. A análise é limitada a YAMLs diretamente em `.github/workflows/`
em PRs do mesmo repositório para `main` ou `laboratorio/auditoria`. Push, scripts
e actions locais alterados fora desse caminho ficam fora do disparo. Um rename
aparece como remoção do caminho antigo e inclusão do novo.

O piloto usa dois jobs independentes. Um job de auditoria que sirva de barreira
para a CI e a proteção de sua dependência contra sugestões de remoção ficam
para a integração em pipelines que exijam essa ordem.

**Impacto:** mudanças fora dos caminhos monitorados são dispensadas. O resumo
distingue essa situação de falha ao obter o diff ou ler um arquivo. A leitura do
workflow que contém o analisador é estática.

O resumo do Actions associa cada relatório ao caminho original e ao SHA. O
campo `source` do relatório aponta para a cópia local preparada pelo script.
Em uma falha de análise, o resumo registra o código de saída da CLI, com
detalhes como linha e causa do erro disponíveis na execução local.

**Referência:** scripts/audit_pull_request.py; .github/workflows/pipeline-audit-lab.yml.

### LIM-038 — Código de saída não certifica correção

**Tipo:** contrato de uso.

O padrão `0` significa análise concluída. Com `--fail-on-warning`, um `warning`
no workflow auditado ou na versão modificada da comparação retorna `1`.
Com apenas oportunidades, o retorno é `0`. Erros de argumentos, entrada ou arquivo
retornam `2`.

**Impacto:** cobertura parcial pode produzir tanto silêncio indevido quanto um
alerta por produtor não reconhecido. Escolher bloquear a CI por qualquer warning
exige considerar esse alcance. Nenhum código de saída aprova integralmente a
pipeline.

**Referência:** cli.py, main(); LIM-002, LIM-025 e LIM-033.

### LIM-039 — Validade e eficácia científica ainda não medidas

**Tipo:** avaliação pendente.

Os testes locais e os 12 pares sintéticos verificam comportamentos da
implementação. Não substituem uma amostra independente do TCC, a reprodução em
runners reais nem uma comparação experimental executada com outras ferramentas.

**Impacto:** ainda não demonstramos precisão geral, cobertura em repositórios
reais, melhoria de duração, superioridade ou segurança das sugestões.
É necessário medir o que reconhecemos e a correção do que concluímos.

**Referência:** tests, cases, registro local de verificação gerado por
scripts/verify.py e próximos passos.

### LIM-040 — Custo das buscas em grafos não estudado

**Tipo:** oportunidade técnica, sem problema de desempenho demonstrado.

ancestors() e descendants() usam DFS com pilha, mas percorrem todas as arestas
ao visitar cada nó. A análise faz várias dessas consultas.

Listas de adjacência foram mencionadas como possível melhoria futura, mas não
medimos um gargalo real nem definimos uma exigência de escala.

**Impacto:** não reivindicar desempenho para grafos grandes sem medições.
Preservar a clareza do código continua sendo uma preferência do projeto.

**Referência:** model.py, Workflow.ancestors()/descendants(); chamadas em analyzer.py.

### LIM-041 — Acesso a outputs e resultados exige dependência direta

**Estado** Corrigido para as referências literais reconhecidas.

O GitHub Actions disponibiliza em `needs` os outputs e resultados das
dependências diretas de um job. A R06 verifica a declaração dessa dependência
na auditoria e em cada versão da comparação.

Considere `build → bridge → verify` e um `verify` que lê
`needs.build.outputs.version`. Mudar `needs: [build, bridge]` para
`needs: bridge` preserva a ordem de `build` antes de `verify` e retira
`build` do contexto `needs` de `verify`. A configuração modificada recebe
`R06_NEEDS_DIRECT_DEPENDENCY` na localização da referência.

Uma condição como `always() && needs.build.result == 'success'` também
exige `needs: build`. Quando a dependência direta existe, a revisão de
paralelismo protege a aresta e registra `direct_needs_protected` em sua
cobertura. Nas transferências de artefatos, a ordem preservada por um caminho
indireto ainda satisfaz a verificação estrutural.

**Limite restante** A regra cobre as referências reconhecidas conforme a
LIM-009. Valores de outputs, resultados reais e referências dinâmicas ficam
fora do modelo.

**Referência** `snapshot()` e `compare()` em `analyzer.py`.
[Contexto needs no GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#needs-context).

## 6. Decisões e correções que não devem voltar como pendências

- **Consulta genérica já implementada.** O interpretador consulta os valores do
  contexto fornecido, com escopo de coleta delimitado pela LIM-014.
- **Classificação histórica removida:** o antigo caso de deslocar um step e
  classificá-lo falsamente como novo/resolvido não é um comportamento atual.
  Hoje o acompanhamento foi adiado, conforme LIM-030.
- **Opção atual da CLI:** --fail-on-warning. A opção antiga para apenas novos
  warnings não faz mais parte do contrato.
- **Análise estática:** não executar os comandos é uma escolha. Este catálogo não
  transforma isso em obrigação de implementar um executor.
- **Não usar IA:** o interpretador determinístico é a abordagem atual, não uma
  deficiência.
- **None:** preservar indeterminação é intencional, não um erro a eliminar.
- **condition():** apenas normaliza o if; a avaliação pertence a evaluate().
- **job_states:** é memória interna de states(); não ser retornado é intencional.

## 7. Regra de atualização daqui para frente

1. Ao identificar uma nova limitação durante a leitura, procurar primeiro se ela
   já está representada neste catálogo.
2. Atualizar o item existente ou acrescentar o próximo identificador, sem
   renumerar os anteriores. O próximo disponível é LIM-042.
3. Registrar o que não é feito, um exemplo ou consequência, a função relacionada
   e se o programa sinaliza a restrição automaticamente.
4. Distinguir falta de conhecimento, recurso não implementado, aproximação,
   requisito futuro e escolha de escopo.
5. Se houver correção, atualizar o estado e registrar a data e a evidência, sem
   manter uma restrição resolvida como se ainda estivesse ativa.
6. Documentar não significa implementar uma solução nem assumir compromisso de
   ampliar o escopo.
7. Manter a data da revisão clara na cópia portátil. O Markdown deste catálogo
   é a fonte de referência; o PDF é sua cópia para leitura.

**Registro inicial:** 27/10/2026, com base na leitura de cli.py, model.py,
conditions.py e da parte atual de analyzer.py, além das restrições já discutidas.
