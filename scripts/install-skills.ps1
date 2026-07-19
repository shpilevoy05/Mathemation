$ErrorActionPreference = "Stop"

# Синхронизация скиллов из agent-skills/ (источник правды) в каталоги обнаружения:
#   .claude/skills/<skill>/  — Claude Code
#   .agents/skills/<skill>/  — Codex
# Запуск: .\scripts\install-skills.ps1

$Root = Split-Path -Parent $PSScriptRoot
$Sources = @()
$Sources += Get-ChildItem -Directory (Join-Path $Root "agent-skills\vendor") | ForEach-Object { Get-ChildItem -Directory $_.FullName }
$MatemaciaDir = Join-Path $Root "agent-skills\matemacia"
if (Test-Path $MatemaciaDir) { $Sources += Get-ChildItem -Directory $MatemaciaDir }

$Targets = @((Join-Path $Root ".claude\skills"), (Join-Path $Root ".agents\skills"))
foreach ($t in $Targets) { New-Item -ItemType Directory -Force $t | Out-Null }

$count = 0
$names = @{}
foreach ($skill in $Sources) {
    if (-not (Test-Path (Join-Path $skill.FullName "SKILL.md"))) {
        Write-Warning "Пропуск (нет SKILL.md): $($skill.FullName)"
        continue
    }
    if ($names.ContainsKey($skill.Name)) {
        Write-Warning "Конфликт имён скиллов: $($skill.Name) ($($names[$skill.Name]) и $($skill.FullName))"
        continue
    }
    $names[$skill.Name] = $skill.FullName
    foreach ($t in $Targets) {
        $dst = Join-Path $t $skill.Name
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Copy-Item -Recurse $skill.FullName $dst
    }
    $count++
}
Write-Host "Установлено скиллов: $count -> .claude\skills и .agents\skills"
