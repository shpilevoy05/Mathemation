param(
    [string]$Path = "agent-skills",
    [switch]$FailOnReview
)
$ErrorActionPreference = "Stop"

# Skills audit v2. Three verdicts:
#   PASS   (exit 0) - automated checks passed
#   REVIEW (exit 1) - potentially dangerous constructs, human review required
#   BLOCK  (exit 2) - installation forbidden (injection, binaries, exfiltration)
# REVIEW hits inside security-education content (attack examples) are expected
# after manual review; only BLOCK gates installation.

$Root = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $Root $Path

$BlockPatterns = @(
    'ignore (all |any )?(previous|prior) instructions',
    'disregard .{0,40}(instructions|system prompt)',
    'do not (tell|inform|reveal to|mention to) the user',
    'hide (this|it) from the user',
    'send .{0,60}(\.env|api[ _-]?key|token|password).{0,60}(http|url|server)'
)
$ReviewPatterns = @(
    'Invoke-Expression|\biex\b\s*\(',
    '(Invoke-WebRequest|curl|wget)[^|]{0,140}\|\s*(ba|z|pwsh|power)?sh',
    'Start-Process',
    'Remove-Item\s+-Recurse',
    'git reset --hard|git clean -[a-z]*f|git push --force',
    '\b(chmod|chown|sudo)\b',
    'verify\s*=\s*False|--insecure|SkipCertificateCheck|NODE_TLS_REJECT_UNAUTHORIZED',
    '\.ssh/|id_rsa|credentials?\.(json|xml|yml)',
    '/etc/(passwd|shadow)',
    'mcpServers|"mcp_servers"',
    'base64 (-d|--decode)|nc -e|reverse shell'
)
$BinaryExtensions = @(".exe", ".dll", ".so", ".dylib", ".bin", ".scr", ".msi")

# These lock-pinned files contain detection signatures or quoted attack examples.
# Keep the allowlist exact: a new path remains BLOCK by default, while matches in
# these manually reviewed files stay visible as REVIEW findings.
$SecurityEducationFiles = @{
    "agent-skills/vendor/sentry/sentry-security-review/references/modern-threats.md" = $true
    "agent-skills/vendor/sentry/skill-scanner/references/prompt-injection-patterns.md" = $true
    "agent-skills/vendor/sentry/skill-scanner/scripts/scan_skill.py" = $true
}

function Get-AuditRelativePath([string]$FullPath) {
    $relative = $FullPath
    if ($relative.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relative = $relative.Substring($Root.Length)
    }
    return $relative.TrimStart([char]92, [char]47).Replace('\', '/')
}

$files = Get-ChildItem -Recurse -File $Target
$blocks = @()
$reviews = @()

foreach ($f in $files) {
    if ($BinaryExtensions -contains $f.Extension.ToLower()) {
        $blocks += ("{0} : binary executable" -f $f.FullName.Replace($Root + '\', ''))
    }
}
$textFiles = $files | Where-Object { $_.Extension -match '^\.(md|ps1|sh|py|js|ts|yaml|yml|json|toml|txt|bats)$' }
foreach ($p in $BlockPatterns) {
    foreach ($h in ($textFiles | Select-String -Pattern $p -ErrorAction SilentlyContinue)) {
        $relativePath = Get-AuditRelativePath $h.Path
        if ($SecurityEducationFiles.ContainsKey($relativePath)) {
            $reviews += ("{0}:{1} [security-education: {2}]" -f $relativePath, $h.LineNumber, $p)
        }
        else {
            $blocks += ("{0}:{1} [{2}]" -f $relativePath, $h.LineNumber, $p)
        }
    }
}
foreach ($p in $ReviewPatterns) {
    foreach ($h in ($textFiles | Select-String -Pattern $p -ErrorAction SilentlyContinue)) {
        $reviews += ("{0}:{1} [{2}]" -f $h.Path.Replace($Root + '\', ''), $h.LineNumber, $p)
    }
}

if ($blocks.Count) {
    Write-Host ("BLOCK: {0}" -f $blocks.Count) -ForegroundColor Red
    $blocks | Select-Object -First 40 | ForEach-Object { Write-Host "  $_" }
    exit 2
}
if ($reviews.Count) {
    Write-Host ("REVIEW: {0} findings - manual review required" -f $reviews.Count) -ForegroundColor Yellow
    $reviews | Select-Object -First 60 | ForEach-Object { Write-Host "  $_" }
    if ($FailOnReview) { exit 1 }
    exit 1
}
Write-Host "PASS: no suspicious constructs found." -ForegroundColor Green
exit 0
