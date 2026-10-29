# Pipeline Impact

Protótipo de análise estática de workflows do GitHub Actions, desenvolvido
para um Trabalho de Conclusão de Curso em Engenharia de Software.

Compara duas configurações locais e gera relatórios de mudanças, relações de
artefatos, condições de execução e oportunidades condicionais de revisão para
paralelismo entre jobs.

Ferramenta: **0.1.0**. Contrato dos relatórios: **schema 0.2**.

## Instalação

Requer Python 3.11 ou superior. Execute na raiz do repositório.

### Windows / PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-repro.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-repro.txt
.venv/bin/python -m pip install -e .
```

## Uso

Exemplo em PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pipeline_impact `
    --before cases/03-artefato-sem-ordem/before.yml `
    --after cases/03-artefato-sem-ordem/after.yml `
    --output reports/exemplo
```

Em Linux/macOS, use `.venv/bin/python` e escreva os argumentos em uma linha
ou use a continuação de linha apropriada ao shell.

O programa cria `report.json` e `report.md` na pasta informada em `--output`.
O Markdown inclui grafos Mermaid; as arestas também estão disponíveis no JSON.
Relatórios gerados não são versionados.

O caso 03 remove uma dependência entre produtor e consumidor de `app`.
O analisador reconhece a relação de dados e aponta a falta de precedência
garantida na configuração modificada.

O programa não executa os comandos nem as actions dos workflows analisados.
No Windows, `demo.ps1` também executa uma demonstração com o caso 05.

## Capacidades

- Ler YAML preservando `on` e rejeitar chaves duplicadas, dependências
  inexistentes e ciclos.
- Construir grafos de dependências entre jobs.
- Comparar jobs, dependências diretas e transitivas, condições, tolerância a
  falhas, steps e outputs.
- Indicar descendentes potencialmente afetados pelas mudanças.
- Reconhecer uploads/downloads por nomes literais de artefatos e verificar
  precedência por posição dos steps ou caminhos entre jobs.
- Identificar, em cenários delimitados, download ativo com uploads anteriores
  reconhecidos pulados.
- Examinar a remoção hipotética de dependências, preservando relações de dados
  reconhecidas, e sugerir revisão para possível paralelismo.

## Interpretação

| Campo ou tipo | Significado |
|---|---|
| `changes` | Diferenças nas propriedades acompanhadas |
| `affected_jobs` | Descendentes potencialmente afetados |
| `after.findings` | Diagnósticos atuais da configuração modificada |
| `warning` | Inconsistência ou risco sob as premissas do modelo |
| `opportunity` | Sugestão condicional que exige revisão e validação |
| `limitations` | Informações ou comportamentos não resolvidos |
| `structurally_unordered_pairs` | Pares sem ordem imposta por dependências |

O contrato atual não classifica achados como novos, persistentes ou resolvidos.
O ID é uma referência técnica, sem correspondência histórica garantida.
Um diagnóstico atual não comprova que a alteração o causou.

### Códigos de saída

- `0`: análise concluída; no modo padrão, pode haver warnings.
- `1`: com `--fail-on-warning`, existe algum warning na versão modificada.
- `2`: erro de entrada, argumentos ou arquivo.

Oportunidades não fazem a opção retornar `1`. O código `0` não certifica a
correção da pipeline.

## Testes e exemplos

O repositório contém uma suíte de testes e 12 pares sintéticos de workflows.
As expectativas estão em `case.json` e `cases/catalog.json`.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/run_cases.py
```

Em Linux/macOS, use `.venv/bin/python`. O primeiro comando executa a suíte;
o segundo gera relatórios locais em `reports/`. Os comandos dos workflows
não são executados por essas verificações.

| Casos | Propriedade estudada |
|---|---|
| 03 e 04 | Ausência de ordem e precedência transitiva preservada |
| 05 e 06 | Upload condicional e consumo protegido |
| 09 e 10 | Sugestão de paralelismo e bloqueio por relação de dados |
| 11 e 12 | Pares sem ordem e sequência necessária preservada |

`scripts/build_cases.py` regenera os casos de desenvolvimento; não é necessário
para usar o analisador. `scripts/verify.py` reúne verificações locais e registra
seus resultados.

## Limites

- A CLI exige dois arquivos locais. Não coleta base de PR, configurações por
  SHA ou histórico. É possível repetir o mesmo caminho nas duas entradas.
- Os cenários predefinidos são push na main, push na feature e pull request
  com uma referência de merge de exemplo. Filtros/configurações de eventos
  ainda suspendem a análise contextual.
- O interpretador cobre um subconjunto de expressões, supondo sucesso dos
  comandos executados, sem simulação completa de falhas ou cancelamentos.
- O reconhecimento de artefatos cobre as actions oficiais de upload/download
  com nomes literais individuais. Scripts, actions personalizadas, nomes
  dinâmicos e transferências externas podem ocultar relações.
- Referências a outputs são reconhecidas por busca textual, sem confirmar sua
  existência nem representar todas as formas de acesso.
- Matrizes, workflows reutilizáveis, concorrência entre steps e grupos
  concurrency não são completamente modelados.
- As oportunidades não provam independência, não alteram YAML e não estimam
  economia. Recursos compartilhados, efeitos externos e barreiras contra
  falhas exigem revisão.

Os casos são materiais de desenvolvimento. Não substituem avaliação
independente nem execução em runners reais. A eficácia da ferramenta e a
comparação experimental com outras soluções ainda precisam ser medidas.

## Estrutura

```text
src/pipeline_impact/   Núcleo, CLI e apresentação dos resultados
tests/                Testes da implementação
cases/                Workflows e expectativas de desenvolvimento
scripts/              Geração dos casos, lote de relatórios e verificação
pyproject.toml        Configuração de instalação
requirements-repro.txt
demo.ps1              Demonstração local no Windows
```
