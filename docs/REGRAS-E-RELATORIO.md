# Regras e relatório

O contrato JSON atual é o 0.2. A ferramenta separa diferenças entre duas
configurações e diagnósticos de uma configuração. Uma mudança não é
automaticamente um defeito.

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
| `schema_version` | Versão do contrato do relatório |
| `tool_version` | Versão da ferramenta |
| `before` e `after` | Resumo e análise individual de cada configuração |
| `changes` | Diferenças nas propriedades acompanhadas e descendentes potencialmente afetados |
| `summary` | Quantidade de registros de mudança e contagem dos tipos de achados da versão modificada |
| `assumptions` | Premissas gerais para interpretar a análise |

Cada snapshot contém `source`, `jobs`, `edges`, `data_relations`,
`structurally_unordered_pairs`, `contexts_checked`, `findings` e `limitations`.

As arestas usam a direção do pré-requisito para o dependente. `data_relations`
registra relações reconhecidas entre jobs, mesmo quando não há precedência
garantida no grafo. `contexts_checked` informa cenários examinados pelo modelo;
não é uma lista de execuções reais.

O campo `source` identifica o arquivo recebido. O relatório não inclui o YAML
completo nem todos os comandos dos steps.

## Estrutura de um achado

Um achado contém `id`, `rule`, `kind`, `jobs`, `artifact`, `context`, `evidence`
e `suggestion`. Campos não aplicáveis podem conter `null`.

- `id` é uma referência técnica calculada a partir do conteúdo do achado.
- `kind` distingue `warning` de `opportunity`.
- `context` identifica o cenário modelado quando o diagnóstico depende dele.
- `evidence` descreve os elementos que sustentam a conclusão.
- `suggestion` informa a revisão proposta, quando aplicável.

A posição de um step começa em 1 para facilitar a leitura; ela não é a linha
do arquivo YAML. Um contexto `null` em R02 indica um diagnóstico estrutural,
não uma condição avaliada como indeterminada.

O contrato não contém classificação histórica como novo, persistente ou
resolvido. O hash do achado também não garante correspondência entre versões.

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

A comparação produz dois registros: mudança de dependência direta e mudança
dos ancestrais de `verify`. O snapshot modificado produz um alerta R02. O
diagnóstico informa perda da garantia de ordem; uma execução pode ainda passar
por circunstâncias de agendamento.

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
`after.findings`; não diferencia alertas novos e preexistentes. Oportunidades
não provocam esse retorno. Erros de argumentos, entrada ou arquivo retornam `2`.

Para analisar uma única configuração pela CLI atual, é possível fornecer o
mesmo arquivo em `--before` e `--after`. Isso produz duas análises individuais e
nenhuma mudança nas propriedades acompanhadas; não é uma opção de auditoria
dedicada.
