# Piloto de análise de PRs no GitHub Actions

## Conferência local

Execute os comandos no PowerShell, na raiz do repositório, com a instalação do
[README](../README.md).

```powershell
.\demo.ps1
.\.venv\Scripts\pipeline-impact.exe `
    --before cases/03-artefato-sem-ordem/before.yml `
    --after cases/03-artefato-sem-ordem/after.yml `
    --output reports/comparacao-03
.\.venv\Scripts\python.exe scripts/verify.py
```

Em `reports/audit-demo`, o caso 03 apresenta um R02 no step 2 de `verify`.
O job tenta baixar `app` sem uma dependência que garanta a precedência de
`build`. Em `reports/comparacao-03`, o alerta acompanha dois registros
de mudança. Um descreve a dependência direta e o outro descreve os ancestrais
de `verify`. Em **Impactos explicados**, confira o vínculo entre a remoção
de `needs: build` e o R02.

Para conferir R03, compare o caso 05 com os contextos do laboratório:

```powershell
.\.venv\Scripts\python.exe -m pipeline_impact `
    --before cases/05-upload-condicional/before.yml `
    --after cases/05-upload-condicional/after.yml `
    --contexts cases/contexts.json `
    --output reports/comparacao-05
```

O vínculo `upload_condition_changed` no cenário de PR deve apontar para o
upload no step 3 de `build` e o alerta no step 2 de `verify`. A versão
anterior ativa o upload. A versão modificada o pula. A restauração apenas do
`if` torna o upload ativo novamente no modelo. O arquivo inclui também um
cenário de push para `feature`, em que o mesmo efeito é esperado. No push
para `main`, o upload continua ativo.

Para conferir a LIM-041 em um relatório, crie os dois YAMLs abaixo em
`reports/comparacao-06/`:

```powershell
New-Item -ItemType Directory -Force reports/comparacao-06 | Out-Null
$workflowAntes = @'
name: Teste de perda de acesso a output
on: push
jobs:
  build:
    runs-on: ubuntu-24.04
    outputs:
      version: ${{ steps.produzir.outputs.value }}
    steps:
      - id: produzir
        run: echo "value=1" >> "$GITHUB_OUTPUT"
  bridge:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - run: echo bridge
  verify:
    needs: [build, bridge]
    runs-on: ubuntu-24.04
    steps:
      - env:
          VERSION: ${{ needs.build.outputs.version }}
        run: echo "$VERSION"
'@
$workflowAntes | Set-Content -Encoding utf8 reports/comparacao-06/before.yml
$workflowAntes.Replace('needs: [build, bridge]', 'needs: bridge') |
    Set-Content -Encoding utf8 reports/comparacao-06/after.yml
.\.venv\Scripts\python.exe -m pipeline_impact `
    --before reports/comparacao-06/before.yml `
    --after reports/comparacao-06/after.yml `
    --output reports/comparacao-06
```

Espere um R06 em `verify`, step 1, campo `env`. O vínculo
`direct_needs_lost` deve identificar a remoção de `build` do `needs` de
`verify` e registrar `order_preserved: true`. O grafo conserva a precedência
por `bridge` e o consumidor perde acesso ao output pelo contexto `needs`.

## Execução no GitHub

Abra PRs do mesmo repositório com destino a `main` ou `laboratorio/auditoria`.
O workflow `pipeline-audit-lab.yml` tem dois jobs independentes, a CI de
laboratório e a análise. O piloto usa o analisador da revisão base. A seleção
considera o diff completo do PR e os arquivos `.yml` e `.yaml` diretamente
em `.github/workflows/`. Para um workflow modificado, o piloto compara o
YAML completo do ancestral comum das branches (`merge-base`) com o YAML
completo da revisão atual do PR (`head`). Arquivos novos são auditados.
Exclusões são registradas no resumo.
[Comparação de branches em PRs](https://docs.github.com/en/pull-requests/reference/branches#about-three-dot-comparison-on-github).

Na aba **Checks** do PR, abra a execução de laboratório e consulte o resumo
do job **Auditoria do PR**. Confira o caminho, o modo, as revisões, as
contagens e a pasta no artefato de cada arquivo. Baixe
`pipeline-audit-reports` para ler o `report.md` e o
`report.json`. Alertas ficam visíveis no relatório em modo de observação.
Falhas de preparação ou análise aparecem como erro no job de análise. Se a
CLI falhar para um arquivo, os relatórios produzidos com sucesso para os
outros arquivos continuam disponíveis. A CI de laboratório roda de forma
independente.
[Eventos de PR](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request) · [Artefatos de workflow](https://docs.github.com/en/actions/tutorials/store-and-share-data).

### Contexto do evento

O job de auditoria lê `GITHUB_EVENT_NAME`, `GITHUB_REF`,
`GITHUB_BASE_REF` e `GITHUB_HEAD_REF` fornecidas pelo GitHub Actions.
O script converte esses campos em um contexto JSON e passa o arquivo à CLI
com `--contexts`. Na comparação, o mesmo contexto é fornecido aos dois YAMLs.
Os relatórios registram os campos recebidos, a compatibilidade do evento
com o gatilho do YAML e os estados estimados dos steps em eventos elegíveis.
[Variáveis do GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/variables#default-environment-variables).

O evento pertence à execução do piloto. A avaliação dos workflows
selecionados continua estática e usa a premissa de sucesso das etapas
ativas. Na comparação, cada versão é avaliada conforme seus gatilhos.
[Contrato do relatório](REGRAS-E-RELATORIO.md) ·
[Limitações LIM-014, LIM-015 e LIM-037](LIMITACOES-DO-PROTOTIPO.md).

### Validação do contexto em um novo PR

1. Confira se a branch de destino já contém o analisador e o workflow do
   piloto da versão 0.4.0. O piloto instala a revisão base do PR.
2. Em uma branch de teste do mesmo repositório, adicione o workflow abaixo
   em `.github/workflows/contexto-pr-lab.yml` e abra um PR para `main`.
   Para testar com destino a `laboratorio/auditoria`, use esse nome em
   `branches` e na condição do primeiro step.
3. No resumo, confira o evento `pull_request`, o SHA do YAML auditado
   e as branches de destino e origem. No artefato do YAML de teste, confira
   `tool_version: "0.4.0"`, `schema_version: "0.5"` e `mode: "audit"`
   em `report.json`.
   A entrada em `analysis.context_evaluations` deve ter
   `event_status: "eligible"` e `step_states.checks: [true, false]`.
4. Para conferir a exclusão pelo gatilho, troque a branch do filtro
   por uma branch diferente do destino do PR. A auditoria deve registrar
   `event_status: "excluded"`, `step_states: {}` e `contexts_checked: []`.

```yaml
name: Teste de contexto de PR
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  checks:
    runs-on: ubuntu-24.04
    steps:
      - name: Conferir destino do PR
        if: github.base_ref == 'main'
        run: echo destino esperado
      - name: Conferir evento de push
        if: github.event_name == 'push'
        run: echo evento push
```

### Cenários do piloto

O arquivo `.github/workflows/caso-03-lab.yml` parte da versão protegida, com
`verify.needs: build`. O gatilho `workflow_dispatch` deixa os jobs de upload e
download fora do disparo automático do PR. O PR dispara a análise estática
do arquivo alterado.

| Cenário | Alteração no PR | Resultado esperado |
|---|---|---|
| Controle sem mudança de workflow | Alterar apenas um arquivo da aplicação de laboratório. | A CI roda. O resumo informa a dispensa e a instalação do analisador é pulada. |
| Perda de precedência | Remover `needs: build` de `verify` no caso 03. | `mode: "compare"`, R02 em `verify`, step 2, e vínculo `artifact_order_lost`. |
| Restauração | No mesmo PR, restaurar `needs: build` e mudar o campo `name` do workflow. | O arquivo continua no diff e recebe comparação com zero mudanças modeladas e sem R02. |
| Duas versões com contexto | Alterar um workflow cujo evento inclui `pull_request`. | O JSON registra o mesmo contexto em `before.context_evaluations` e `after.context_evaluations`, com os resultados de elegibilidade de cada versão. |
| Base avançada | Na base de laboratório, fazer um commit independente que altere o mesmo YAML sem conflito com o PR. | A revisão anterior registrada para a comparação é o ancestral comum. As mudanças da base feitas após a divergência ficam fora do diff analisado. |
| Dois arquivos | Alterar um workflow em um commit e adicionar outro em um segundo commit. | Um par de relatórios por arquivo, com `mode: "compare"` no modificado e `mode: "audit"` no novo. |
| Exclusão | Excluir um workflow da base. | O resumo registra a exclusão. Esse caminho não recebe relatórios. |
| Renomeação | Renomear um workflow da base dentro de `.github/workflows/`. | O caminho antigo é registrado como exclusão e o novo recebe uma auditoria. |
| Falha em um arquivo | No teste local de integração, preparar um lote com um YAML válido e outro inválido. | A CLI falha para o YAML inválido. Os relatórios bem-sucedidos são preservados, e o job de análise termina com erro. |

Se a restauração deixar o arquivo idêntico à base, ele sai do diff completo.
Mantenha a alteração em `name` para observar a nova comparação.

No caso 03, confira se `before` mostra a aresta de `build` para `verify`, se
`after.findings` contém R02 e se `impact_links` aponta para esse alerta e para
o registro R01 de dependência direta. Guarde o link da execução, o SHA do
analisador da base, o ancestral comum, o `head` do PR e os relatórios usados.

## Registro histórico do piloto de auditoria

O piloto executou os cenários abaixo com base no commit
`4ea330ceb897ef22f3baa9e6d91aa4202e8041d8`. Os jobs de auditoria e da CI
concluíram com sucesso nas quatro execuções. [PR de laboratório](https://github.com/ziansouzab/tcc-pipeline-analizer/pull/1).

| Cenário | SHA do PR | Resultado observado | Execução |
|---|---|---|---|
| Controle | `eca19cf1c6ed71ff6f40c061653ebec07bdbc4da` | Instalação e análise dispensadas. Nenhum artefato. | [Controle](https://github.com/ziansouzab/tcc-pipeline-analizer/actions/runs/42928417629) |
| Perda de precedência | `c6dd7da3c2ca912effcdcf9b6b6d86c5eaa3914c` | Um par de relatórios, com R02 em `verify`, step 2. | [R02](https://github.com/ziansouzab/tcc-pipeline-analizer/actions/runs/42928623351) |
| Restauração | `9fbb435441694a2f35ad5b21a3132ea785c9cf1e` | Um par de relatórios, com zero alertas. | [Restauração](https://github.com/ziansouzab/tcc-pipeline-analizer/actions/runs/42928709447) |
| Múltiplos arquivos e renomeação | `9a3dc76bc0ec25b14970a78d74c65f914e46d8cd` | Dois pares de relatórios. O diff do mesmo SHA registra o caminho antigo como exclusão. | [Múltiplos arquivos](https://github.com/ziansouzab/tcc-pipeline-analizer/actions/runs/42928766824) |

A primeira execução de controle falhou na resolução da action de upload. O
commit `4ea330c` corrigiu o SHA da action e o controle passou ao reabrir o PR.
[Execução inicial](https://github.com/ziansouzab/tcc-pipeline-analizer/actions/runs/42928206838).

As cópias locais do ZIP, dos relatórios e dos metadados das execuções estão em
`reports/piloto-github/`. Os resultados de auditoria e comparação em casos
separados estão no [protocolo de avaliação](PROTOCOLO-AVALIACAO.md).
