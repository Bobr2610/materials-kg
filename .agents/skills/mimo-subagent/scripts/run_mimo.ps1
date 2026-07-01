[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,

    [string]$Model = "mimo/mimo-auto",

    [string]$TaskSlug = "mimo-task",

    [string]$OutputRoot = ".",

    [switch]$Json
)

$mimoShim = "C:\Users\misha\AppData\Roaming\npm\mimo.cmd"
$mimoExe = $null

if (Get-Command mimo -ErrorAction SilentlyContinue) {
    $mimoExe = "mimo"
} elseif (Test-Path -LiteralPath $mimoShim) {
    $mimoExe = $mimoShim
} else {
    throw "MiMo CLI not found. Install @mimo-ai/cli or ensure mimo.cmd is available."
}

$date = Get-Date -Format "yyyyMMdd"
$safeSlug = ($TaskSlug -replace '[^a-zA-Z0-9._-]', '-').Trim('-')
if ([string]::IsNullOrWhiteSpace($safeSlug)) {
    $safeSlug = "mimo-task"
}

$targetDir = Join-Path $OutputRoot "docs\mimo-runs\$date\$safeSlug"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$promptFile = Join-Path $targetDir "00_prompt.txt"
$summaryFile = Join-Path $targetDir "20_summary.md"
Set-Content -LiteralPath $promptFile -Value $Prompt -Encoding UTF8

$args = @("run", "-m", $Model)

if ($Json) {
    $args += @("--format", "json")
}

$args += $Prompt

$output = & $mimoExe @args 2>&1
$exitCode = $LASTEXITCODE

if ($Json) {
    $rawFile = Join-Path $targetDir "10_raw_output.jsonl"
    Set-Content -LiteralPath $rawFile -Value $output -Encoding UTF8
} else {
    Set-Content -LiteralPath $summaryFile -Value $output -Encoding UTF8
}

if ($exitCode -ne 0) {
    throw "MiMo run failed with exit code $exitCode. Output saved to $targetDir"
}

Write-Output $targetDir
