$ErrorActionPreference = 'Stop'
$demoRoot = $PSScriptRoot
$demoPython = Join-Path $demoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    throw 'Crie o ambiente conforme o README.md antes de executar a demonstração.'
}
$beforeWorkflow = Join-Path $demoRoot 'cases/05-upload-condicional/before.yml'
$afterWorkflow = Join-Path $demoRoot 'cases/05-upload-condicional/after.yml'
$reportDirectory = Join-Path $demoRoot 'reports/demo'

& $demoPython -m pipeline_impact `
    --before $beforeWorkflow `
    --after $afterWorkflow `
    --output $reportDirectory

if ($LASTEXITCODE -ne 0) {
    throw "A análise falhou com código $LASTEXITCODE."
}
