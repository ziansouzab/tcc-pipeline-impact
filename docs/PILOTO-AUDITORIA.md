# Piloto de auditoria no GitHub Actions

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
`build`. Em `reports/comparacao-03`, o mesmo alerta acompanha dois registros
de mudança. Um descreve a dependência direta e o outro descreve os ancestrais
de `verify`.

## Execução no GitHub

Abra PRs do mesmo repositório com destino a `laboratorio/auditoria`. O workflow
`pipeline-audit-lab.yml` tem dois jobs independentes, a CI de laboratório e a
auditoria. O auditor usa o analisador da revisão base e lê os YAMLs no SHA da
revisão do PR. A seleção considera o diff completo do PR e os arquivos
`.yml` e `.yaml` diretamente em `.github/workflows/`.

Na aba **Checks** do PR, abra a execução de laboratório e consulte o resumo
do job de auditoria. Confira o caminho e o SHA registrado para cada arquivo.
Baixe os artefatos para ler o `report.md` e o `report.json`. Alertas ficam
visíveis no relatório e permitem que a auditoria termine em modo de observação.
Falhas de preparação ou análise aparecem como erro no job de auditoria. A CI
de laboratório executa em ambos os casos.
[Eventos de PR](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request) · [Artefatos de workflow](https://docs.github.com/en/actions/tutorials/store-and-share-data).

### Cenários do piloto

O arquivo `.github/workflows/caso-03-lab.yml` parte da versão protegida, com
`verify.needs: build`. O gatilho `workflow_dispatch` deixa os jobs de upload e
download fora do disparo automático do PR. O PR dispara a auditoria estática
do arquivo alterado.

| Cenário | Alteração no PR | Resultado esperado |
|---|---|---|
| Controle sem mudança de workflow | Alterar apenas um arquivo da aplicação de laboratório. | A CI roda. O resumo informa auditoria dispensada e o analisador não é instalado. |
| Perda de precedência | Remover `needs: build` de `verify` no caso 03. | R02 em `verify`, step 2, com dois relatórios disponíveis. |
| Restauração | No mesmo PR, restaurar `needs: build` e mudar o campo `name` do workflow. | O arquivo continua alterado em relação à base e recebe uma nova auditoria sem R02. |
| Dois arquivos | Alterar um workflow em um commit e adicionar outro em um segundo commit. | Um par de relatórios por arquivo, incluindo o alterado no primeiro commit. |
| Exclusão | Excluir um workflow da base. | O resumo registra a exclusão. Esse caminho não recebe relatórios. |
| Renomeação | Renomear um workflow da base dentro de `.github/workflows/`. | O caminho antigo é registrado como exclusão e o novo recebe uma auditoria. |

Se a restauração deixar o arquivo idêntico à base, ele sai do diff completo.
Mantenha a alteração em `name` para observar a nova auditoria.

## Registro para o TCC

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
