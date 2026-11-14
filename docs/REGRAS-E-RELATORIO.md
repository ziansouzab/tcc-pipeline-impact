# Regras e relatório

O contrato JSON 0.6 identifica a auditoria de um workflow e a comparação de
versões. A auditoria apresenta diagnósticos de uma configuração. A comparação
acrescenta as mudanças entre configurações e os vínculos demonstrados com
alertas da versão modificada.

## Verificações e resultados

| Identificação | O que representa | Onde aparece |
|---|---|---|
| `R01_JOB_CHANGE` | Adição ou remoção de job | `changes` |
| `R01_DEPENDENCY_CHANGE` | Alteração nas dependências diretas | `changes` |
| `R01_REACHABILITY_CHANGE` | Alteração nos ancestrais, inclusive transitivos | `changes` |
| `R02_ARTIFACT_ORDER` | Download sem produtor reconhecido de mesmo nome com precedência garantida | `findings`, tipo `warning` |
| `R03_ARTIFACT_CONDITION` | Download ativo e todos os uploads anteriores reconhecidos pulados em um contexto modelado | `findings`, tipo `warning` |
| `R04_CONDITION_CHANGE` | Alteração da condição de um job | `changes` |
| `R04_FAILURE_POLICY_CHANGE` | Alteração de `continue-on-error` | `changes` |
| `R05_PARALLEL_REVIEW` | Dependência candidata à revisão para possível paralelismo | `findings`, tipo `opportunity` |
| `R06_NEEDS_DIRECT_DEPENDENCY` | Referência a output ou resultado de job fora das dependências diretas do consumidor | `findings`, tipo `warning` |

Também são registradas mudanças na lista de steps (`STEP_CHANGE`), nos outputs
(`OUTPUT_CHANGE`), nos eventos (`TRIGGER_CHANGE`) e em propriedades sem
regras próprias (`UNMODELED_JOB_CHANGE` e `UNMODELED_WORKFLOW_CHANGE`).
Esses registros podem receber explicações pelo campo.

Pares de jobs sem ordem imposta pelo grafo aparecem em
`structurally_unordered_pairs`. Os casos 11 e 12 mantêm `R06` em
`plan_rule` como rótulo do plano inicial. O identificador de diagnóstico
da versão atual é `R06_NEEDS_DIRECT_DEPENDENCY`.

## Estrutura principal

| Campo | Conteúdo |
|---|---|
| `schema_version` | `0.6` |
| `tool_version` | `0.5.0` |
| `mode` | `audit` para auditoria ou `compare` para comparação |
| `analysis` | Snapshot do workflow auditado, presente no modo `audit` |
| `before` e `after` | Snapshots das duas configurações, presentes no modo `compare` |
| `changes` | Diferenças nas propriedades acompanhadas e descendentes potencialmente afetados, presentes no modo `compare` |
| `step_changes` | Detalhes das mudanças nos steps de jobs presentes nas duas versões, disponíveis no modo `compare` |
| `impact_links` | Vínculos entre mudanças e alertas demonstrados no modelo estático, presentes no modo `compare` |
| `summary` | Contagens de `warning` e `opportunity` na auditoria. Na comparação, preserva a quantidade de mudanças e os tipos de achados da versão modificada |
| `assumptions` | Premissas gerais para interpretar a análise |

Cada snapshot contém `source`, `jobs`, `edges`, `data_relations`,
`structurally_unordered_pairs`, `contexts_checked`, `context_evaluations`,
`findings`, `coverage` e `limitations`.

As arestas usam a direção do pré-requisito para o dependente. `data_relations`
registra pares de jobs relacionados por artefatos e por referências reconhecidas
a outputs ou resultados, inclusive nos casos sem precedência garantida no
grafo. `contexts_checked` informa os cenários admitidos pelos gatilhos e
examinados pelo modelo.

O campo `source` identifica o arquivo recebido. O relatório não inclui o YAML
completo nem todos os comandos dos steps.

O Markdown apresenta alertas, oportunidades e mudanças antes dos grafos.
Vínculos em `impact_links` são mostrados junto aos alertas. A cobertura igual
nas duas versões aparece uma vez e fica disponível para consulta.

## Explicações das mudanças

Cada registro de `changes` e `step_changes` contém uma lista `explanations`.
Cada item informa `field`, `status` e `message`. O estado `explained`
indica um efeito sustentado pela configuração ou pelo cenário. O estado
`indeterminate` indica que a interpretação exige dados adicionais ou uma
correspondência de steps. O estado `detected` indica que o campo mudou.

Quando publicáveis, `before` e `after` mostram valores da configuração.
`context_comparisons` reúne o mesmo `context` e os estados `before` e
`after` para gatilhos e condições. Os valores dos comandos, ambientes e
parâmetros de actions permanecem no YAML. `affected_jobs` descreve o
alcance potencial no grafo ou o escopo do workflow.

O efeito pode ser estrutural, como a manutenção de uma ordem por um
caminho indireto, ou declarativo, como a mudança do limite de execução ou
da política de cancelamento em um grupo de concorrência. A explicação por
campo e a demonstração de vínculo com um alerta têm evidências próprias.

## Contextos de evento

A opção `--contexts` recebe um arquivo JSON em UTF-8 com uma lista de objetos.
Em cada objeto, `github.event_name` deve ser um texto não vazio. Os campos
opcionais `github.ref`, `github.base_ref`, `github.head_ref`,
`github.repository`, `github.event.pull_request.head.repo.full_name` e
`github.event.before` aceitam texto não vazio ou `null`. Os campos são chaves
planas. Chaves fora desse conjunto, chaves repetidas e contextos duplicados
geram erro de entrada. [Arquivo de exemplo](../cases/contexts.json).

Exemplo de contexto com referências de um pull request.

```json
[
  {
    "github.event_name": "pull_request",
    "github.ref": "refs/pull/42/merge",
    "github.base_ref": "main",
    "github.head_ref": "ajuste-ci"
  }
]
```

Sem `--contexts` ou com lista vazia, a avaliação de condições fica suspensa. Com
contextos, cada avaliação em `context_evaluations` registra o objeto recebido,
`event_status`, a justificativa em `reason`, `job_states` e `step_states`. A elegibilidade
tem três situações possíveis. `eligible` admite a avaliação de jobs e steps.
`excluded` indica evento ausente ou excluído pelo gatilho.
`indeterminate` indica dados insuficientes ou gatilho fora do subconjunto
interpretado. Em contextos elegíveis, `job_states` associa cada job ao seu
estado e `step_states` organiza os estados por job na ordem dos steps.
Os valores `true`, `false` e `null` representam ativo, pulado e
indeterminado no modelo. O mesmo conjunto de contextos é avaliado para cada
configuração no modo de comparação.

Para um evento declarado sem filtros, a avaliação verifica o nome do evento.
Em `push` e `pull_request`, também se admite um único filtro `branches` ou
`branches-ignore` com nomes literais. O filtro usa a branch de `github.ref`
em `push` e a branch de destino de `github.base_ref` em `pull_request`.
Push de tag é excluído por filtros de branch. Padrões, filtros de caminhos,
combinações de filtros e parâmetros não interpretados podem deixar a
elegibilidade indeterminada para o contexto. [Catálogo, LIM-013 a LIM-016](LIMITACOES-DO-PROTOTIPO.md).

## Alterações nos steps

`STEP_CHANGE` continua em `changes` como registro agregado da mudança de lista
por job. `step_changes` detalha as mudanças de jobs presentes nas duas versões
com os tipos `added`, `removed`, `modified`, `reordered` e `unmatched`.
Cada registro indica o job, as posições e os rótulos disponíveis em cada versão.
As posições `before_step` e `after_step` contam a partir de 1. Os rótulos
`before_name` e `after_name` usam o `name` ou, na ausência dele, o `id`.

A correspondência considera o `id` único no job, sem distinção de maiúsculas
e minúsculas, seguido pelo `name` único entre candidatos, pelo conteúdo
equivalente sem `id` e `name` e pela action literal de um step sem nome.
Para actions externas, o caminho anterior ao `@` permite reconhecer uma
troca de versão. Actions locais e imagens Docker usam a referência literal
completa. Em steps sem nome, o último critério compara o comando inalterado.
Cada critério exige um par único entre os candidatos disponíveis.
Casos com indícios de correspondência e sem par único podem aparecer como
`unmatched`. A prioridade entre critérios faz parte da aproximação
documentada na LIM-029.

`reordered` registra a inversão da ordem entre steps correspondentes em um
job sequencial suportado. Um deslocamento de posição causado apenas por
inserção ou remoção conserva a ordem relativa dos steps restantes.

`fields` inclui os valores anterior e atual de `name`, `if`,
`continue-on-error` e `uses` literal quando o tipo de dado é suportado.
Outras alterações aparecem pelo nome do campo em `other_fields`. O relatório
preserva os valores de `run`, `env` e `with` no arquivo de origem. Para um
`if` alterado com correspondência, `context_comparisons` compara os estados
modelados no mesmo contexto. Os resultados possíveis são `active`, `skipped`,
`indeterminate` e `event_excluded`. A interpretação de
`continue-on-error` descreve um efeito possível sob falha.
[Catálogo, LIM-016, LIM-029 e LIM-030](LIMITACOES-DO-PROTOTIPO.md).

## Estrutura de um achado

Um achado contém `id`, `rule`, `kind`, `jobs`, `artifact`, `context`, `evidence`,
`suggestion` e `location`. Campos não aplicáveis podem conter `null`.

- `id` é uma referência técnica calculada a partir do conteúdo do achado.
- `kind` distingue `warning` de `opportunity`.
- `context` identifica o cenário modelado quando o diagnóstico depende dele.
- `evidence` descreve os elementos que sustentam a conclusão.
- `suggestion` informa a revisão proposta, quando aplicável.
- `location` aponta o job consumidor e a posição do step em R02 e R03. Em R05,
  aponta o job dependente e o campo `needs`. Em R06, indica o job consumidor,
  o campo em que a referência foi encontrada e a posição do step quando
  aplicável.

A posição do step conta a partir de 1 na lista de steps do job. Um contexto
`null` em R02 ou R06 identifica um diagnóstico estrutural. O analisador
registra a localização ao criar o achado e mantém esse campo fora do cálculo
do ID.

O contrato não contém classificação histórica como novo, persistente ou
resolvido. O hash do achado também não garante correspondência entre versões.

## Impactos explicados

A seção **Impactos explicados** do Markdown descreve os vínculos que a
comparação demonstrou entre uma mudança e um alerta da versão modificada.
Em JSON, cada item em `impact_links` contém os seguintes campos.

| Campo | Conteúdo |
|---|---|
| `type` | Tipo de impacto identificado |
| `change_index` | Índice em `changes`, contado a partir de 0 |
| `finding_id` | ID do alerta em `after.findings` |
| `location` | Localização do alerta na versão modificada |
| `evidence` | Evidência estruturada do que foi verificado no modelo |
| `step_change_index` | Índice em `step_changes`, contado a partir de 0, no vínculo com R03 |
| `context` | Contexto de evento usado no vínculo com R03 |

| Tipo | Verificação |
|---|---|
| `artifact_order_lost` (R02) | O upload e o download reconhecidos ainda são identificáveis. Havia precedência na versão anterior. Recolocar uma aresta removida na versão modificada restabelece a ordem entre produtor e consumidor. |
| `direct_needs_lost` (R06) | A mesma referência literal a output ou resultado permanece no consumidor. O produtor saiu de seu `needs` direto, inclusive quando continua antecedendo o consumidor por outro caminho. |
| `upload_condition_changed` (R03) | No mesmo contexto elegível, o download continua ativo e o upload passa de ativo para pulado. Restaurar apenas o `if` anterior do upload no modelo da versão modificada volta a ativá-lo antes do download. |

Em `evidence`, todos os tipos identificam `producer_job` e `consumer_job`.
As demais propriedades variam com a verificação.

- **R02** registra `artifact`, `removed_edge` na ordem
  `[pré-requisito, dependente]` e os booleanos `precedence_before`,
  `precedence_after` e `precedence_with_restored_edge`.
- **R06** registra `reference`, `removed_edge` e `order_preserved`. O
  último indica se a ordem estrutural foi preservada por outro caminho.
- **R03** registra `artifact`, as posições `producer_step_before`,
  `producer_step_after`, `consumer_step_before` e `consumer_step_after`,
  contadas a partir de 1, e os estados `upload_state_before`,
  `upload_state_after` e `upload_state_with_restored_if`.

A lista fica vazia quando as verificações deixam o vínculo sem demonstração.
`after.findings` continua sendo o campo para consultar todos os achados da
versão modificada. Os resultados descrevem propriedades do modelo estático
e consideram somente relações reconhecidas. [Limitações LIM-030 e
LIM-031](LIMITACOES-DO-PROTOTIPO.md).

## Cobertura de cada snapshot

O campo `coverage` contém registros para a avaliação de condições
(`condition_evaluation`), o reconhecimento de artefatos
(`artifact_recognition`), a ordem dos artefatos (`R02_ARTIFACT_ORDER`), suas
condições (`R03_ARTIFACT_CONDITION`), a revisão de paralelismo
(`R05_PARALLEL_REVIEW`) e as dependências diretas de referências ao contexto
`needs` (`R06_NEEDS_DIRECT_DEPENDENCY`). Cada registro contém `analysis`,
`scope`, `status`, `reasons` e `details`. `reasons` é uma lista de textos.
Cada item de `details` contém `result` e `message` e pode incluir `location`,
`context`, `edge`, `protected_relation`, `action`, `references` ou `artifact`.

| `status` | Rótulo no relatório | Interpretação |
|---|---|---|
| `executed` | Executada | A verificação ocorreu no escopo indicado |
| `partial` | Parcial | Parte dos elementos ou cenários ficou fora da verificação ou indeterminada |
| `suspended` | Suspensa | Uma condição impediu a verificação no escopo indicado |
| `not_applicable` | Não aplicável | O workflow não apresentou elementos pertinentes no escopo modelado |

Os detalhes incluem produtores e consumidores reconhecidos, seletores não
suportados, jobs não resolvidos, contextos examinados e condições indeterminadas.
Na avaliação de condições, `missing_event_data` indica um campo conhecido
ausente, `runtime_value` indica um dado indisponível da execução,
`unsupported_context` indica uma propriedade fora do modelo e
`unsupported_expression` indica uma expressão fora do subconjunto. A R03
considera a incerteza que afeta a transferência examinada. Sem consumidores
pertinentes no reconhecimento, a verificação condicional de artefatos é
classificada como não aplicável.
Para paralelismo, registram motivos de suspensão, dependências examinadas,
ordem preservada por outro caminho e relações de dados protegidas. O detalhe
`direct_needs_protected` identifica a aresta e a relação cuja referência
exige a dependência direta. Actions fora do reconhecimento de artefatos aparecem
como fronteira da análise, de acordo com LIM-002 e LIM-034.
[Catálogo de limitações](LIMITACOES-DO-PROTOTIPO.md).

As situações se referem ao escopo registrado para cada análise. Para interpretar
uma saída sem alertas, examine `coverage`, `limitations` e `assumptions`.

## Exemplo do caso 03

Antes da mudança, `verify` declara `needs: build`. Depois, essa dependência é
removida. As duas configurações ainda descrevem o upload de `app` em `build` e o
download em `verify`.

| Informação | Antes | Depois |
|---|---|---|
| Arestas de dependência | `build -> verify` | Nenhuma |
| Relação de dados reconhecida | `build -> verify` | `build -> verify` |
| Precedência reconhecida do produtor | Sim | Não |
| Alerta R02 | Ausente | Presente |

A auditoria de `after.yml` produz um grafo e um alerta R02 com `location` igual a
`{"job": "verify", "step": 2}`. O download de `app` pode acontecer antes da
disponibilização do artefato. Na comparação, `changes` registra a alteração da
dependência direta e dos ancestrais de `verify`.

## Exemplo de acesso ao contexto needs

Considere a ordem `build → bridge → verify`. O job `verify` usa
`${{ needs.build.outputs.version }}` em um step e declara
`needs: [build, bridge]`. Se a declaração mudar para `needs: bridge`,
`build` continua sendo um ancestral de `verify`. O acesso ao output depende
da declaração direta e a versão modificada recebe R06. A mesma verificação
se aplica a `needs.build.result`. Um upload em `build` e um download em
`verify` podem manter a precedência estrutural por meio de `bridge`.
[Contexto needs no GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#needs-context).

A R06 verifica o workflow na auditoria ou cada versão na comparação,
independentemente do contexto de evento. A regra procura referências literais
a outputs e resultados em expressões `${{ ... }}` nos valores de jobs e steps.
O campo `if` de jobs e steps também é examinado quando a expressão aparece
sem delimitadores. Texto comum e literais de texto dentro das expressões
ficam fora da busca.
São aceitos acessos por ponto e por colchetes com chave textual literal,
como `needs['build'].outputs['version']`. A comparação dos IDs de job
ignora diferenças de maiúsculas e minúsculas.

`evidence` registra `producer_job`, `reference`, `reason` e os campos
de localização do consumidor. A referência
é apresentada com pontos, inclusive quando a expressão usa colchetes.
A cobertura registra `executed` ao verificar acessos reconhecidos e
`not_applicable` quando nenhum acesso é reconhecido. A regra verifica a
declaração da dependência direta. A obtenção dos valores e a disponibilidade
do contexto em cada campo ficam fora do modelo.
[Catálogo, LIM-009 e LIM-041](LIMITACOES-DO-PROTOTIPO.md).

## Premissas que afetam a leitura

R02 considera produtores locais reconhecidos e precedência estrutural. R03
considera os cenários suportados e o estado calculado dos steps. Um upload ativo
no modelo não comprova existência dos arquivos nem sucesso efetivo da action.

R05 verifica uma aresta por vez. Preserva a dependência direta exigida por
referências ao contexto `needs` e a precedência que já existia nas relações
de artefatos reconhecidas. Recursos compartilhados, efeitos externos,
estimativa de economia e remoção automática ficam fora dessa revisão.

`affected_jobs` reúne descendentes potencialmente afetados. Uma lista vazia
pode indicar que o job modificado é terminal; não significa ausência de impacto
na própria etapa. A ocorrência de um alerta em `after.findings` não comprova que
a mudança o introduziu.

`limitations: []` não comprova cobertura completa. Consulte as restrições por
categoria no [catálogo](LIMITACOES-DO-PROTOTIPO.md).

## Política da CLI

As entradas devem ser workflows em UTF-8, com ou sem BOM, e conter valores
serializáveis em JSON. Tipos YAML como datas implícitas, binários e conjuntos,
assim como números não finitos e aliases recursivos, recebem erro de entrada.
Quando uma data for um valor textual, escreva-a entre aspas no YAML.

O modo padrão retorna `0` quando a análise termina, mesmo com alertas.
`--fail-on-warning` retorna `1` se houver qualquer `warning` em
`analysis.findings` na auditoria ou em `after.findings` na comparação.
Com apenas oportunidades, o retorno é `0`. Erros de argumentos, entrada ou arquivo
retornam `2`.

Use `pipeline-impact audit caminho.yml` para auditar um arquivo ou
`pipeline-impact --before antes.yml --after depois.yml` para comparar dois.
Ambos aceitam `--contexts`, `--output` e `--fail-on-warning`. Por exemplo,
`pipeline-impact audit cases/05-upload-condicional/after.yml --contexts cases/contexts.json`
avalia o caso condicional com os contextos dos testes. As opções `--before` e `--after`
pertencem à comparação. A CLI rejeita combinações dessas opções com `audit` e
protege os arquivos de entrada contra sobrescrita pelo relatório.
