$ErrorActionPreference = 'Stop'
$demoRoot = $PSScriptRoot
$demoPython = Join-Path $demoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    throw 'Crie o ambiente conforme o README.md antes de executar a demonstração.'
}
$workflowPath = Join-Path $demoRoot 'cases/03-artefato-sem-ordem/after.yml'
$reportDirectory = Join-Path $demoRoot 'reports/audit-demo'

& $demoPython -m pipeline_impact audit $workflowPath `
    --output $reportDirectory

if ($LASTEXITCODE -ne 0) {
    throw "A análise falhou com código $LASTEXITCODE."
}
