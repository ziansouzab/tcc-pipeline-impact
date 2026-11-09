# Próximos passos

A versão atual compara dois arquivos locais. O próximo marco é colocar esse
diagnóstico em um ambiente experimental do GitHub Actions, preservando o núcleo
e o contrato dos relatórios.

Nenhum workflow de integração do analisador é fornecido nesta etapa. Os itens
abaixo são requisitos para a próxima implementação, não funcionalidades prontas.

## Primeiro marco no GitHub Actions

Uma alteração em um workflow deve produzir este percurso:

1. Detectar mudanças nos caminhos de pipeline monitorados.
2. Identificar e obter as configurações anterior e modificada corretas.
3. Preparar o ambiente Python e executar a CLI existente.
4. Disponibilizar o resumo e os arquivos de relatório para consulta.
5. Registrar quando a análise foi dispensada ou quando a comparação não pôde
   ser obtida.

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

A CLI atual exige dois workflows existentes e não vazios. Adições, exclusões e
renomeações de arquivos precisam de uma política própria na integração. Não se
deve substituir silenciosamente um arquivo ausente por um workflow vazio,
porque esse arquivo não atende à entrada atual.

Falha ao obter o diff, a revisão ou o arquivo não equivale a ausência de
mudanças. A integração deve registrar esse erro de preparação e manter claro
quais configurações foram efetivamente analisadas.

## Critérios do primeiro experimento

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
