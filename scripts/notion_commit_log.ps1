param(
  [Parameter(Mandatory=$true)]
  [string]$DatabaseId,

  # valores por defecto (deben existir como opciones en tus selects)
  [string]$DefaultArea = "Código",
  [string]$DefaultStatus = "Done"
)

# 1) Asegurar que estamos en el root del repo
$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) { exit 0 }
Set-Location $repoRoot

# 2) Datos del commit
$sha      = git rev-parse HEAD
$shortSha = git rev-parse --short HEAD
$subject  = git log -1 --pretty=%s
$body     = git log -1 --pretty=%b
$branch   = git rev-parse --abbrev-ref HEAD
$remote   = (git config --get remote.origin.url)
$files    = @(git diff-tree --no-commit-id --name-only -r HEAD)

# 3) Heurística simple para Área (puedes tunearla)
$area = $DefaultArea
if ($subject -match "^(design|diseño|ux|ui)\s*:" ) {
  $area = "Diseño"
} elseif ($files | Where-Object { $_ -match '\.(png|svg|jpg|jpeg|webp)$' -or $_ -match '(^|/)(design|assets)/' }) {
  $area = "Diseño"
}

# 4) Campos DB
$date = Get-Date -Format "yyyy-MM-dd"
$time = Get-Date -Format "HH:mm:ss"

$repoBranch = if ($remote) { "$remote @ $branch" } else { $branch }

$filesText = if ($files.Count -gt 0) { ($files | ForEach-Object { "- $_" }) -join "`n" } else { "- (sin cambios detectados)" }
$bodyText  = if ($body) { "`n`n$body" } else { "" }

$name    = "$subject ($shortSha)"
$resumen = "[$time] $subject`n`nArchivos:`n$filesText$bodyText"
$acciones = "- [x] Commit registrado"

# 5) Prompt para Codex (vía MCP Notion)
$prompt = @"
Usa las herramientas MCP de Notion.

Crea UN nuevo registro (page) en la base de datos con id: $DatabaseId

Rellena EXACTAMENTE estas propiedades (respeta nombres y valores):
- Name (title): "$name"
- Fecha (date): "$date"
- Área (select): "$area"
- Resumen (rich text): "$resumen"
- Acciones (rich text): "$acciones"
- Repo/Branch (rich text): "$repoBranch"
- Status (select): "$DefaultStatus"

No modifiques archivos locales. No ejecutes comandos adicionales.
Devuelve solo: OK
"@

# Ejecuta Codex en modo no interactivo. Lee el prompt de stdin.
# -s read-only mantiene el sandbox en solo lectura (ideal para un hook). :contentReference[oaicite:3]{index=3}
$prompt | codex exec -s read-only -C $repoRoot - | Out-Null
