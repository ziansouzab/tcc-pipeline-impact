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

Guarde os links das execuções, os SHAs e os relatórios como evidência do
piloto. Preencha uma linha por cenário e anote o resultado observado antes de
encerrar o PR.

| Cenário | Link da execução | SHA da base e do PR | Arquivo e relatórios | Resultado observado |
|---|---|---|---|---|
|  |  |  |  |  |

Para avaliar a hipótese, fixe o commit do analisador e prepare casos
independentes dos 12 pares de desenvolvimento. Registre o diagnóstico
esperado e a justificativa de cada caso antes de consultar a ferramenta. Na
condição A, audite a versão modificada. Na condição B, compare as duas versões
do mesmo caso. Avalie se o diagnóstico e a localização correspondem à
expectativa e se a comparação acrescenta uma explicação correta da mudança.
Registre também alertas indevidos, problemas não apontados e análises
indeterminadas.

| Caso e SHAs | Diagnóstico esperado e justificativa | A — diagnóstico e localização | B — explicação da mudança | Avaliação |
|---|---|---|---|---|
|  |  |  |  |  |
