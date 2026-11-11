# Próximos passos

A versão atual audita um workflow local e compara duas versões. A branch
`laboratorio/auditoria` usa a auditoria em PRs controlados com o mesmo núcleo
de análise e contrato de relatórios. [Roteiro do piloto](PILOTO-AUDITORIA.md).

O próximo marco de integração é automatizar a comparação entre as versões de um
PR. Os requisitos a seguir orientam essa extensão.

## Integração da comparação no GitHub Actions

Uma alteração em um workflow deve produzir este percurso:

1. Detectar mudanças nos caminhos de pipeline monitorados.
2. Identificar o arquivo e a revisão que serão analisados. Para uma comparação,
   identificar as duas versões.
3. Preparar o ambiente Python e executar a auditoria ou a comparação pela CLI.
4. Disponibilizar o resumo e os arquivos de relatório para consulta.
5. Registrar as análises dispensadas e os erros de preparação.

Os caminhos iniciais monitorados serão os workflows `.yml` e `.yaml` de
`.github/workflows/`. Scripts e actions locais poderão ser acrescentados por
configuração explícita, sem presumir descoberta de todas as dependências.

No PR, a seleção deve considerar as mudanças do conjunto do PR em relação à
base, e não apenas o último commit. As versões usadas precisam acompanhar a
evidência produzida. No push, a comparação deve considerar os estados anterior
e novo informados pelo evento.

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

O modo inicial será de observação, disponibilizando os alertas para revisão.
Qualquer política de bloqueio deve considerar os códigos da CLI e os limites
das regras; ausência de alerta não é aprovação completa da pipeline.

## Entradas que exigem tratamento explícito

`audit` exige um workflow existente e não vazio. A comparação exige dois
arquivos válidos. A integração pode auditar um arquivo adicionado. Para
exclusões, deverá registrar a ausência do arquivo na revisão atual. Para
renomeações, deverá identificar os caminhos e as revisões disponíveis.

A integração deve registrar falhas ao obter o diff, a revisão ou o arquivo como
erros de preparação e indicar quais configurações foram efetivamente analisadas.

## Critérios para ampliar o experimento

- Alteração apenas na aplicação dispensa o analisador e mantém a CI.
- Alteração em workflow executa a análise com versões identificadas.
- O caso de artefato sem ordem produz o diagnóstico esperado e relatórios
  acessíveis.
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
Executar a ferramenta no Actions também não preencherá automaticamente os
contextos fixos do interpretador.

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
