# Protocolo de avaliação do TCC

## Avaliação da análise de impacto em PRs

A unidade de avaliação é uma alteração de workflow. No piloto, use um PR e
consulte o relatório do workflow modificado. Localmente, execute uma
comparação por par de YAMLs. A avaliação verifica quais impactos a ferramenta
identifica e se a explicação liga a alteração ao alerta por meio de evidência.

1. Fixe o commit do analisador e registre versão, schema e data.
2. Antes de consultar o relatório, registre a mudança, os impactos esperados,
   a regra, a localização e o contexto. Guarde os SHAs ou hashes das entradas
   e a justificativa obtida pela inspeção manual da configuração.
3. Consulte `changes`, `step_changes`, `after.findings` e `impact_links`.
   Para cada vínculo, confira se a mudança, o alerta, a localização e a
   evidência correspondem à expectativa. Use os snapshots e a cobertura
   para interpretar resultados indeterminados.
4. Separe acertos, omissões e vínculos indevidos. Um alerta correto pode
   permanecer sem vínculo quando a mudança que lhe deu origem estiver fora
   do subconjunto. Registre alertas preexistentes na ficha com base nas
   evidências das duas versões.
5. No Actions, guarde também o link da execução, o SHA do analisador da base,
   o ancestral comum, o `head` e os relatórios. Qualquer execução do workflow
   analisado para observar o impacto deve ser registrada separadamente.

Para conferir a implementação, use os casos 03 (R02), 05 (R03) e LIM-041
(R06) do [roteiro do piloto](PILOTO-AUDITORIA.md#conferência-local). Inclua
controles de precedência transitiva preservada, alerta preexistente,
condição indeterminada e steps com correspondência ambígua. Para a avaliação
do TCC, monte uma amostra com expectativas próprias, cobrindo impactos
verificáveis, mudanças legítimas e situações fora do subconjunto. Os casos
de desenvolvimento servem como verificação da implementação.

## Procedimento preliminar da versão 0.2.0

O registro abaixo conserva o desenho usado no piloto anterior.

A auditoria (A) analisa apenas a versão atual. A comparação (B) recebe a
versão anterior e a mesma versão atual. O objetivo é verificar a correção
dos achados e medir quais informações verificáveis sobre a mudança B
acrescenta a A. Os dois modos compartilham a análise da versão atual, então
é esperado que produzam os mesmos achados sobre esse arquivo.

### Preparação

1. Fixe o commit do analisador e registre a versão, o schema e a data.
2. Use `before.yml` e `after.yml` de cada pasta em `evaluation/`. Os pares
   usam jobs de laboratório e actions oficiais de transferência de artefatos.
3. Revise manualmente os YAMLs e registre os hashes, o comportamento esperado,
   os jobs e steps relevantes e os limites do modelo. Guarde esse registro antes
   de consultar as saídas. Documente qualquer ajuste posterior ao protocolo.

Os quatro cenários são sintéticos e foram especificados para esta avaliação.
Os 12 pares de `cases/` continuam servindo às verificações de desenvolvimento.
[Catálogo de limitações, LIM-039](LIMITACOES-DO-PROTOTIPO.md).

### Casos e expectativas

| Caso | Par de configurações | Esperado na auditoria da versão atual | Evidência adicional esperada na comparação |
|---|---|---|---|
| [E01 — Nome de artefato divergente](../evaluation/E01-nome-divergente) | `pack` publica `bundle` e `metadata`. `verify` tem `needs: pack` e baixa os dois nessa ordem. A versão atual renomeia apenas o upload de `bundle` para `bundle-v2`. | Um R02 em `verify`, step 1, para `bundle`. O download de `metadata` conserva a precedência e protege a dependência de uma sugestão R05. | Mudança nos steps de `pack`, com `verify` como descendente potencialmente afetado. O grafo permanece igual e o alerta de `bundle` está ausente na versão anterior. |
| [E02 — Condição no mesmo job](../evaluation/E02-condicao-no-job) | `review` cria um arquivo no step 1, publica `evidence` no step 2 e baixa `evidence` no step 3. Os eventos são `push` e `pull_request`. A versão atual restringe apenas o upload a `github.event_name == 'pull_request'`. | R03 em `review`, step 3, nos cenários de `push` em `main` e `feature`. No cenário de PR o upload está ativo. A ordem dos steps preserva a precedência estrutural. | Mudança nos steps de `review` e alertas condicionais apenas na versão atual. |
| [E03 — Dependência com output](../evaluation/E03-dependencia-output) | `pack` declara o output `label` a partir de um step, e `publish` declara `needs: pack`. O step de `publish` usa um rótulo fixo na versão anterior e `${{ needs.pack.outputs.label }}` na versão atual, via variável de ambiente. | A relação `pack → publish` aparece em `data_relations`. A cobertura de R05 registra a proteção da dependência. | Mudança nos steps de `publish`, com grafo preservado. A versão anterior apresenta a oportunidade R05, enquanto a atual registra a relação de dados. |
| [E04 — Análise condicional suspensa](../evaluation/E04-filtro-de-evento) | `pack` publica `evidence` em um step com condição `github.ref == 'refs/heads/main'`. `verify` depende de `pack` e baixa o artefato. A versão atual restringe o evento `push` à branch `main`. | R03 suspensa com motivo ligado ao filtro de evento e sem alerta condicional. R02 reconhece a precedência estrutural. | Mudança no gatilho, com o grafo preservado. A configuração anterior admite a avaliação do cenário `push` em `feature` e apresenta R03 nesse cenário. |

Em E02, o download usa um diretório distinto do arquivo de origem para
facilitar uma eventual execução controlada. Em E03, a expectativa é sobre o
reconhecimento da referência ao output. Esses cenários registram expectativas
anteriores à coleta dos resultados. [Regras e contrato do relatório](REGRAS-E-RELATORIO.md).

### Coleta e conferência

- Para cada caso, rode `pipeline-impact audit <atual>` e
  `pipeline-impact --before <anterior> --after <atual>` com diretórios de
  saída separados. Guarde JSON e Markdown de ambos.
- Confira cada achado pela regra, localização e contexto, quando aplicável.
  Marque as ocorrências esperadas como encontradas ou ausentes e registre
  ocorrências inesperadas. Registre cobertura suspensa separadamente.
- Confira em B as mudanças, o alcance no grafo e os contrastes entre as
  versões. Conte quantas dessas informações corretas foram acrescentadas em
  cada caso. Uma linha de mudança e um alerta são unidades distintas.
- Registre por caso a expectativa, a saída A, a saída B, a evidência consultada
  e a justificativa da classificação. Se houver reprodução no Actions, registre
  o link, o SHA e o comportamento observado dos jobs e steps.

Relate os resultados por cenário e explicite o tamanho e a origem sintética
da amostra. A evidência do piloto documenta o acionamento e a entrega dos
relatórios. A associação com o histórico de execução fica para outro marco.

### Resultados preliminares

As expectativas e os pares foram registrados no commit `a00a9b2` antes da
execução. A avaliação local usou a versão 0.2.0, schema 0.3, com o núcleo do
commit `e5e0db7`. Os relatórios estão em `reports/avaliacao/`, com saídas
separadas por caso e por modo.

| Caso | Auditoria da versão atual | Informação acrescentada pela comparação |
|---|---|---|
| E01 | Um R02 em `verify`, step 1, para `bundle`. A cobertura de R05 protege a dependência pela relação de dados que permaneceu. | `STEP_CHANGE` em `pack`, com `verify` como descendente afetado. O alerta está ausente na versão anterior. |
| E02 | Dois R03 em `review`, step 3, nos cenários de push em `main` e `feature`. | `STEP_CHANGE` em `review`. Os dois alertas estão ausentes na versão anterior. |
| E03 | A relação de dados entre `pack` e `publish` protege a dependência. | `STEP_CHANGE` em `publish`. A versão anterior apresenta R05 no campo `needs`. |
| E04 | R03 suspensa pelo filtro de evento, com a precedência de artefato reconhecida por R02. | `TRIGGER_CHANGE`. A versão anterior apresenta R03 no cenário de push em `feature`. |

Os dois modos produziram a mesma análise da versão atual nos quatro pares.
Os grafos foram preservados. Em cada par, a comparação registrou uma alteração
e permitiu contrastar achados ou cobertura com a versão anterior. Esses
resultados descrevem a análise estática de quatro cenários sintéticos. O
efeito de incorporar histórico ainda requer avaliação.
