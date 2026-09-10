param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$Model = 'qwen3.5:9b'
)

# These values apply only to this process and children. No persistent OS edits.
if ($Model -match 'cloud') {
    throw 'This launcher only runs local models.'
}
$env:UNIHIVE_LLM_PROVIDER = 'ollama'
$env:UNIHIVE_LLM_BASE_URL = 'http://127.0.0.1:11434'
$env:UNIHIVE_LLM_MODEL = $Model
$env:UNIHIVE_LLM_CONTEXT = '16384'
$env:UNIHIVE_LLM_TIMEOUT = '180'
$env:UNIHIVE_LLM_API_KEY = ''
$engineCommand = Join-Path $PSScriptRoot '.venv\Scripts\unihive.exe'
if (-not (Test-Path -LiteralPath $engineCommand)) {
    throw 'Install the project virtual environment as described in README.md.'
}
& $engineCommand analyze --input $InputPath --output $OutputPath
exit $LASTEXITCODE
