# Install MV Maker as a user-level skill for Claude Code (~/.claude/skills) and Codex (~/.agents/skills).
# Uses directory junctions pointing at this clone, so `git pull` updates the skill everywhere.
#   powershell -ExecutionPolicy Bypass -File install.ps1            # both tools
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Only claude
param([ValidateSet("all", "claude", "codex")] [string]$Only = "all")
$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "skills\mv-maker"
$targets = @()
if ($Only -in "all", "claude") { $targets += Join-Path $HOME ".claude\skills\mv-maker" }
if ($Only -in "all", "codex")  { $targets += Join-Path $HOME ".agents\skills\mv-maker" }
foreach ($t in $targets) {
    New-Item -ItemType Directory -Force (Split-Path $t) | Out-Null
    if (Test-Path $t) {
        $item = Get-Item $t -Force
        if ($item.LinkType) { $item.Delete() } else { Write-Host "[mv] $t exists and is not a link - skipped"; continue }
    }
    New-Item -ItemType Junction -Path $t -Target $src | Out-Null
    Write-Host "[mv] linked $t -> $src"
}
& (Join-Path $src "setup.ps1")
Write-Host "`n[mv] Done. Restart Claude Code / Codex, then ask: 'make a lyric video from my poster' or run: $src\mv.cmd demo story"
