# Pipeline Impact

Protótipo de análise de workflows do GitHub Actions.

## Etapa disponível

Tratamento de UTF-8, valores YAML incompatíveis com JSON e cinco regressões.

## Preparação local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-repro.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Os componentes são acrescentados nesta sequência de commits reconstruída para apresentar a organização do protótipo.
