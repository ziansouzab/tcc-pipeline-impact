# Avaliação do Pipeline Impact 0.5.0

O protocolo contém 12 pares sintéticos de workflows, dois contextos de pull request e as expectativas registradas antes da execução. O objetivo é conferir alertas (R02, R03 e R06), vínculos de impacto e cobertura. Cada par é uma unidade de análise. Os casos de desenvolvimento e a suíte de testes estão em [cases](../../cases) e [tests](../../tests).

A revisão da implementação é [257759e](https://github.com/ziansouzab/tcc-pipeline-analizer/tree/257759e60c96fc1c23597d276ab54dfb3d996421), com esquema 0.6. A avaliação usa Python 3.11 ou superior e PyYAML 6.0.3. Na raiz do repositório, execute em um ambiente Python preparado:

```sh
python -m pip install -r requirements-repro.txt
git archive --format=zip --output=fonte-257759e.zip 257759e60c96fc1c23597d276ab54dfb3d996421 src pyproject.toml requirements-repro.txt
python evaluation/0.5.0/executar_avaliacao.py fonte-257759e.zip resultados-avaliacao-050
```

O script confere o commit contido no arquivo fonte e os hashes das entradas. A pasta de saída deve ser nova. Ela recebe um relatório JSON e um Markdown por par, além de `resultado.json` com os resultados consolidados. O script registra a concordância de cada caso em `conforme_protocolo`.

Os contextos deste protocolo são simulados, inclusive quando a CLI é executada em um runner do GitHub Actions. As execuções do piloto com contexto do evento real são descritas na [documentação da integração](../../docs/PILOTO-AUDITORIA.md).
