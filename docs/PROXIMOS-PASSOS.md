# Próximos passos

A versão atual audita um workflow local e compara duas versões. O piloto no
GitHub Actions compara workflows modificados em PRs para `main` ou
`laboratorio/auditoria`, audita arquivos novos e registra exclusões. O próximo
marco é reproduzir o fluxo em uma branch de laboratório que já contenha o
analisador atualizado. [Roteiro do piloto](PILOTO-AUDITORIA.md).

## Extensões da integração

O piloto monitora workflows `.yml` e `.yaml` diretamente em
`.github/workflows/`. Scripts e actions locais poderão ser acrescentados por
configuração explícita. Uma futura integração por push pode usar os estados
anterior e novo informados pelo evento.

## Disparo e preservação da CI

Quando houver apenas alteração na aplicação, o analisador deve ser dispensado
e a CI da aplicação deve continuar normalmente. Um detector leve pode fazer
essa decisão antes de instalar e chamar o núcleo Python.

Em uma CI compartilhada, não se deve colocar um filtro de caminhos no workflow
inteiro se isso impedir também os jobs da aplicação. A primeira integração deve
tratar separadamente a decisão de chamar o analisador e a execução das demais
etapas.

Se o analisador for um job inicial do qual outros jobs dependem, sua conclusão
precisa manter a barreira de ordenação, inclusive quando a análise for
dispensada. Essa dependência deve ser protegida de sugestões de remoção. Ler o
workflow que contém o próprio analisador não provoca recursão, pois a ferramenta
apenas lê o YAML.

O piloto disponibiliza os alertas para revisão em modo de observação.
Qualquer política futura de bloqueio deve considerar os códigos da CLI e os
limites das regras.

## Entradas que exigem tratamento explícito

`audit` exige um workflow existente e não vazio. A comparação exige dois
arquivos válidos. O piloto registra exclusões e trata renomeações como exclusão
e inclusão. Falhas ao obter o diff, a revisão ou o arquivo aparecem como erros
de preparação.

## Critérios para ampliar o experimento

- Alteração apenas na aplicação dispensa o analisador e mantém a CI.
- Alteração em workflow executa a análise com o ancestral comum e o
  `head` identificados.
- Os casos de R02, R03 e R06 produzem os vínculos esperados, com relatórios
  acessíveis e controles registrados.
- Adição, exclusão e renomeação de workflow recebem tratamento explícito.
- Erro de preparação é distinguido de análise dispensada.
- A barreira do job inicial não recebe proposta de remoção.

As primeiras reproduções devem observar a execução e o pulo dos jobs, a ordem
dos steps e a disponibilidade dos artefatos. Uma execução que passa não elimina,
sozinha, um risco de precedência.

## Histórico em uma etapa posterior

Uma coleta separada poderá salvar observações reais para importação na análise.
Cada observação precisará identificar repositório, workflow, revisão, execução,
tentativa e correspondência inequívoca com os jobs. Dados incompatíveis ou
ausentes não deverão ser misturados nem substituídos por duração zero.

O histórico poderá contextualizar resultados e durações observados e apoiar a
priorização dos achados. Uma falha histórica não comprovará a causa de um alerta,
e dados da versão anterior não comprovarão o comportamento da versão modificada.
O contexto de evento fornecido pelo Actions descreve a execução do piloto.
A associação com execuções anteriores exige uma coleta separada.

## Evoluções fora do primeiro marco

Geração de YAML, integração com LLM, expansão de matrizes e workflows
reutilizáveis, paralelismo entre steps e simulação completa de falhas ficam
fora da integração inicial. O suporte e as pendências atuais estão registrados
no [catálogo de limitações](LIMITACOES-DO-PROTOTIPO.md), especialmente
LIM-013 a LIM-019 e LIM-035 a LIM-039.

## Documentação de referência para a integração

- [Sintaxe de workflows do GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): gatilhos, filtros e dependências de jobs.
- [API de execuções](https://docs.github.com/en/rest/actions/workflow-runs): identificação e consulta das execuções.
- [API de jobs e tentativas](https://docs.github.com/en/rest/actions/workflow-jobs): resultados e horários dos jobs por execução ou tentativa.
