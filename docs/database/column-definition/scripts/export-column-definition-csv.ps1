[CmdletBinding()]
param(
    [string]$Workbook = '',
    [string]$OutputDir = '',
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguments = @((Join-Path $scriptDirectory 'export-column-definition-csv.py'))

if (-not [string]::IsNullOrWhiteSpace($Workbook)) {
    $arguments += @('--workbook', $Workbook)
}
if (-not [string]::IsNullOrWhiteSpace($OutputDir)) {
    $arguments += @('--output-dir', $OutputDir)
}
if ($Check) {
    $arguments += '--check'
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCommand) {
    & $pythonCommand.Source @arguments
} else {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (-not (Test-Path -LiteralPath $bundledPython)) {
        throw 'Python 3을 찾지 못했습니다. Python을 PATH에 추가한 뒤 다시 실행하세요.'
    }
    & $bundledPython @arguments
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
