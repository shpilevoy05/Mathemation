#requires -Version 5.1
<#
.SYNOPSIS
    Валидация этого скилла. Логика — scripts/lib/validate_skill.py.
#>
[CmdletBinding()]
param([switch]$Strict)

$ErrorActionPreference = 'Stop'
$skill = Split-Path -Parent $PSScriptRoot
# skill -> matemacia -> agent-skills -> корень репозитория
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $skill))
# Сплаттинг хэштейблом: массив биндится позиционно и -Strict уходит в $Path.
$forward = @{ Path = @($skill) }
if ($Strict) { $forward['Strict'] = $true }
& (Join-Path $repoRoot 'scripts\validate-skills.ps1') @forward
exit $LASTEXITCODE