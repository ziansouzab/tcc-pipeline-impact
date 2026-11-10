# Regras e relatório

O contrato JSON 0.3 identifica a auditoria de um workflow e a comparação de
versões. A auditoria apresenta diagnósticos de uma configuração. A comparação
acrescenta as mudanças entre configurações.

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

Também são registradas mudanças na lista de steps (`STEP_CHANGE`), nos outputs
(`OUTPUT_CHANGE`), nos eventos (`TRIGGER_CHANGE`) e em propriedades sem
interpretação comportamental (`UNMODELED_JOB_CHANGE` e
`UNMODELED_WORKFLOW_CHANGE`).

Não existe um achado emitido como `R06` nesta versão. Pares de jobs sem ordem
imposta pelo grafo aparecem em `structurally_unordered_pairs`.

## Estrutura principal

| Campo | Conteúdo |
|---|---|
| `schema_version` | `0.3` |
| `tool_version` | `0.2.0` |
| `mode` | `audit` para auditoria ou `compare` para comparação |
| `analysis` | Snapshot do workflow auditado, presente no modo `audit` |
| `before` e `after` | Snapshots das duas configurações, presentes no modo `compare` |
| `changes` | Diferenças nas propriedades acompanhadas e descendentes potencialmente afetados, presentes no modo `compare` |
| `summary` | Contagens de `warning` e `opportunity` na auditoria. Na comparação, preserva a quantidade de mudanças e os tipos de achados da versão modificada |
| `assumptions` | Premissas gerais para interpretar a análise |

Cada snapshot contém `source`, `jobs`, `edges`, `data_relations`,
`structurally_unordered_pairs`, `contexts_checked`, `findings`, `coverage` e
`limitations`.

As arestas usam a direção do pré-requisito para o dependente. `data_relations`
registra relações reconhecidas entre jobs, mesmo quando não há precedência
garantida no grafo. `contexts_checked` informa cenários examinados pelo modelo;
não é uma lista de execuções reais.

O campo `source` identifica o arquivo recebido. O relatório não inclui o YAML
completo nem todos os comandos dos steps.

Consumidores do contrato 0.2 devem aceitar `schema_version` igual a `0.3` e
ler `mode` para escolher o snapshot. Na comparação, `before`, `after` e
`changes` mantêm seus significados. O conteúdo de `evidence` e os IDs dos
achados continuam compatíveis com a versão anterior.

## Estrutura de um achado

Um achado contém `id`, `rule`, `kind`, `jobs`, `artifact`, `context`, `evidence`,
`suggestion` e `location`. Campos não aplicáveis podem conter `null`.

- `id` é uma referência técnica calculada a partir do conteúdo do achado.
- `kind` distingue `warning` de `opportunity`.
- `context` identifica o cenário modelado quando o diagnóstico depende dele.
- `evidence` descreve os elementos que sustentam a conclusão.
- `suggestion` informa a revisão proposta, quando aplicável.
- `location` aponta o job consumidor e a posição do step em R02 e R03. Em R05,
  aponta o job dependente e o campo `needs`.

A posição do step conta a partir de 1 na lista de steps do job. Um contexto
`null` em R02 identifica um diagnóstico estrutural. O analisador registra a
localização ao criar o achado e mantém esse campo fora do cálculo do ID.

O contrato não contém classificação histórica como novo, persistente ou
resolvido. O hash do achado também não garante correspondência entre versões.

## Cobertura de cada snapshot

O campo `coverage` contém registros para o reconhecimento de artefatos
(`artifact_recognition`), a ordem dos artefatos (`R02_ARTIFACT_ORDER`), suas
condições (`R03_ARTIFACT_CONDITION`) e a revisão de paralelismo
(`R05_PARALLEL_REVIEW`). Cada registro contém `analysis`, `scope`, `status`,
`reasons` e `details`. `reasons` é uma lista de textos. Cada item de `details`
contém `result` e `message` e pode incluir `location`, `context`, `edge`,
`protected_relation`, `action` ou `artifact`.

| `status` | Rótulo no relatório | Interpretação |
|---|---|---|
| `executed` | Executada | A verificação ocorreu no escopo indicado |
| `partial` | Parcial | Parte dos elementos ou cenários ficou fora da verificação ou indeterminada |
| `suspended` | Suspensa | Uma condição impediu a verificação no escopo indicado |
| `not_applicable` | Não aplicável | O workflow não apresentou elementos pertinentes no escopo modelado |

Os detalhes incluem produtores e consumidores reconhecidos, seletores não
suportados, jobs não resolvidos, contextos examinados e condições indeterminadas.
Para paralelismo, registram motivos de suspensão, dependências examinadas,
ordem preservada por outro caminho e relações de dados protegidas. Actions fora
do reconhecimento de artefatos aparecem como fronteira da análise, de acordo
com LIM-002 e LIM-034. [Catálogo de limitações](LIMITACOES-DO-PROTOTIPO.md).

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

## Premissas que afetam a leitura

R02 considera produtores locais reconhecidos e precedência estrutural. R03
considera os cenários suportados e o estado calculado dos steps. Um upload ativo
no modelo não comprova existência dos arquivos nem sucesso efetivo da action.

R05 verifica uma aresta por vez e preserva relações de dados reconhecidas que
tinham precedência no modelo original. Ela não examina todos os recursos
compartilhados ou efeitos externos, não estima economia e não autoriza uma
remoção automática de dependência.

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
Ambos aceitam `--output` e `--fail-on-warning`. As opções `--before` e `--after`
pertencem à comparação. A CLI rejeita combinações dessas opções com `audit` e
protege os arquivos de entrada contra sobrescrita pelo relatório.
