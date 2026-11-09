# Pipeline Impact

Protótipo de análise de workflows do GitHub Actions.

## Etapa disponível

Grafo de jobs com consultas de ancestrais e descendentes por DFS.

## Preparação local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-repro.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Os componentes são acrescentados nesta sequência de commits reconstruída para apresentar a organização do protótipo.
