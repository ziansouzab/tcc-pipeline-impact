# Desenvolvimento

O projeto utiliza Python 3.11 ou superior, PyYAML e a biblioteca padrão de
testes `unittest`. Siga a [instalação do README](../README.md#instalação) antes
dos comandos abaixo.

## Padrão de escrita

- Use nomes descritivos e variáveis intermediárias para tornar cada decisão legível.
- Prefira `for`, `if`, `elif`, `else` e retornos explícitos.
- Escreva buscas com um laço e uma variável de resultado, em vez de condensá-las
  em compreensões, expressões geradoras ou chamadas a `any`, `all` e `next`.
- Preserve o tratamento de `None`: indeterminação faz parte do modelo.
- Mantenha as explicações na documentação. Não adicione comentários ou docstrings
  ao código.
- Ao refatorar, preserve os resultados dos casos e o contrato dos relatórios,
  salvo quando uma mudança de comportamento for explicitamente necessária.

## Testes da implementação

No PowerShell, na raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

No Linux ou macOS:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

A suíte cobre modelo, condições, análise, relatórios, CLI e expectativas dos
casos de desenvolvimento. Os auxiliares compartilhados ficam em
`tests/helpers.py`.

Ao alterar o parser, examine tanto entradas válidas quanto erros de tipo,
dependências e ciclos. Ao alterar condições, confira resultados determinados,
indeterminados e construções não suportadas. Ao alterar as regras, utilize
controles em que uma relação legítima não deve gerar o mesmo alerta.

## Casos de desenvolvimento

Cada diretório em `cases/` contém `before.yml`, `after.yml` e `case.json`.
O catálogo consolidado fica em `cases/catalog.json`. As expectativas indicam
mudanças ou achados esperados, regras que devem estar ausentes e propriedades
estruturais pertinentes.

| Casos | Propriedade principal |
|---|---|
| 01 e 02 | Adição de dependência e reordenação de uma lista equivalente |
| 03 e 04 | Perda de precedência e preservação de caminho transitivo |
| 05 e 06 | Upload condicional e consumidor com condição compatível |
| 07 e 08 | Alterações de condição e política de falha |
| 09 e 10 | Sugestão de revisão e proteção de uma relação de dados |
| 11 e 12 | Pares sem ordem e sequência preservada |

Os 12 pares são sintéticos e pertencem ao desenvolvimento. Não devem ser
apresentados como amostra independente de avaliação científica.

## Scripts disponíveis

### Gerar relatórios dos casos

```powershell
.\.venv\Scripts\python.exe scripts/run_cases.py
```

O script analisa os pares do catálogo e grava os relatórios em `reports/`,
incluindo `development-results.json`. Ele não executa os comandos dos workflows.

### Reunir verificações locais

```powershell
.\.venv\Scripts\python.exe scripts/verify.py
```

O script reúne a suíte, a conferência de dependências, os relatórios dos casos e
as demonstrações de auditoria e comparação pela CLI. Grava `verification.json`
com os comandos, os resultados e hashes dos arquivos-fonte. O registro fica
na máquina local, fora do Git. As verificações cobrem a implementação local.

Execute `./demo.ps1` no PowerShell para auditar `after.yml` do caso 03. O script
usa o Python de `.venv` e grava os relatórios em `reports/audit-demo`. O caso
produz um alerta R02 e retorna `0` no modo padrão.

### Regenerar os casos

```powershell
.\.venv\Scripts\python.exe scripts/build_cases.py
```

Esse comando reescreve os materiais de desenvolvimento a partir de suas
definições. Use-o somente quando quiser atualizar os casos e confira o diff dos
arquivos gerados. Não é necessário para instalar ou utilizar o analisador.

Nos sistemas Unix, substitua o executável dos exemplos por `.venv/bin/python`.

## Arquivos locais

Ambientes virtuais, caches, `egg-info`, relatórios gerados, registros de
verificação e materiais pessoais de estudo permanecem fora do Git. A
documentação técnica publicada é selecionada explicitamente.

## Antes de concluir uma alteração

Confira o diff e os testes pertinentes. Descreva mudanças de comportamento,
contrato ou cobertura na documentação correspondente. Consulte o
[catálogo de limitações](LIMITACOES-DO-PROTOTIPO.md) antes de registrar um novo
item e preserve seus identificadores.

Organize os commits por mudanças reais e revisáveis: estrutura, refatoração,
correção de comportamento ou documentação. Não reconstrua retrospectivamente
uma sequência fictícia de implementação.
