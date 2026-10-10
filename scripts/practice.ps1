param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PracticeArgs
)
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentName = 'agent-learn'
$environmentCandidates = @()
if ($env:CONDA_PREFIX) { $environmentCandidates += $env:CONDA_PREFIX }
if ($env:CONDA_PYTHON_EXE) {
    $condaRoot = Split-Path -Parent $env:CONDA_PYTHON_EXE
    $environmentCandidates += Join-Path $condaRoot "envs\$environmentName"
}
$environmentRegistry = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.conda\environments.txt'
if (Test-Path -LiteralPath $environmentRegistry) {
    $environmentCandidates += Get-Content -LiteralPath $environmentRegistry
}
$environmentRoot = $environmentCandidates | Where-Object {
    (Split-Path -Leaf $_) -eq $environmentName -and
    (Test-Path -LiteralPath (Join-Path $_ 'python.exe')) -and
    (Test-Path -LiteralPath (Join-Path $_ 'conda-meta/history'))
} | Select-Object -First 1
if (!$environmentRoot) {
    throw 'Named Conda environment agent-learn is missing. Run: conda env create --file environment.yml; conda activate agent-learn'
}
$environmentPython = Join-Path $environmentRoot 'python.exe'
if (!(Test-Path -LiteralPath $environmentPython) -or !(Test-Path -LiteralPath (Join-Path $environmentRoot 'conda-meta/history'))) {
    throw 'Named Conda environment agent-learn is incomplete.'
}
Push-Location $projectRoot
$previousPath = $env:PATH
try {
    $env:PATH = "$environmentRoot;$(Join-Path $environmentRoot 'Scripts');$(Join-Path $environmentRoot 'Library\bin');$previousPath"
    & $environmentPython -X utf8 (Join-Path $projectRoot 'practice.py') @PracticeArgs
    $practiceExitCode = $LASTEXITCODE
} finally {
    $env:PATH = $previousPath
    Pop-Location
}
exit $practiceExitCode
