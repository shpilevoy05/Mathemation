param([string]$Path = "agent-skills")
$ErrorActionPreference = "Stop"

# Грубый аудит скиллов на prompt-injection / эксфильтрацию / опасные команды.
# Находки — повод для РУЧНОГО просмотра, не автоматический вердикт.

$Root = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $Root $Path
$Patterns = @(
    'ignore (all |any )?(previous|prior) instructions',
    'disregard .{0,30}instructions',
    'do not (tell|inform|reveal to) the user',
    'curl[^|]{0,120}\|\s*(ba)?sh',
    'wget[^|]{0,120}\|\s*(ba)?sh',
    'base64 (-d|--decode)',
    'nc -e|reverse shell',
    '\.ssh/|id_rsa',
    'Invoke-Expression|iex \('
)
$regex = ($Patterns -join '|')
$hits = Get-ChildItem -Recurse -File $Target -Include *.md,*.ps1,*.sh,*.py,*.js,*.yaml,*.yml,*.json |
    Select-String -Pattern $regex -AllMatches -ErrorAction SilentlyContinue

if ($hits) {
    Write-Host ("Matches found: {0} - review each manually:" -f $hits.Count) -ForegroundColor Yellow
    $hits | ForEach-Object { Write-Host ("{0}:{1}" -f $_.Path.Replace($Root + '\', ''), $_.LineNumber) }
    exit 1
}
Write-Host "No suspicious patterns found." -ForegroundColor Green