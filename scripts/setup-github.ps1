# Configura GitHub para RetroGameLog: repositorio, etiquetas, hitos, issues y tablero.
# Requisitos: gh instalado, `gh auth login` hecho y `gh auth refresh -s project` (para el tablero).
# Ejecutar desde la raiz del repositorio, despues del primer commit.

# En PowerShell 5.1, "Stop" convierte en error fatal cualquier salida por stderr de gh o git,
# asi que se usa "Continue" y se revisa el codigo de salida de cada comando importante.
$ErrorActionPreference = "Continue"
function Assert-Ok($what) {
    if ($LASTEXITCODE -ne 0) { throw "Fallo: $what (codigo $LASTEXITCODE)" }
}
$owner = "SBMICH"
$repo = "$owner/retrogamelog"

function Write-Utf8NoBom($path, $text) {
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

# 1. Repositorio (publico) y subida de la rama main
gh repo view $repo *> $null
if ($LASTEXITCODE -ne 0) {
    gh repo create $repo --public --source . --remote origin --description "Diario y catalogo de videojuegos retro. Sin ROMs."
    Assert-Ok "crear el repositorio"
}
git push -u origin main
Assert-Ok "git push"

# 2. Etiquetas
$labels = @(
    @("v0.1", "0e8a16", "Catalogo y registro personal"),
    @("v0.2", "1d76db", "Comunidad"),
    @("v0.3", "5319e7", "Descubrimiento"),
    @("v0.4", "fbca04", "RetroAchievements"),
    @("idea", "c5def5", "Idea sin version asignada"),
    @("backend", "bfd4f2", "API y base de datos"),
    @("frontend", "d4c5f9", "React"),
    @("docs", "0075ca", "Documentacion")
)
foreach ($l in $labels) {
    gh label create $l[0] --color $l[1] --description $l[2] --force --repo $repo
    Assert-Ok "etiqueta $($l[0])"
}

# 3. Hitos
foreach ($m in @("v0.1", "v0.2", "v0.3", "v0.4")) {
    gh api "repos/$repo/milestones" -f title=$m -f state=open | Out-Null
    Assert-Ok "hito $m"
}

# 4. Issues: titulo, version, etiquetas extra, historia
$issues = @(
    @("H1 Registro e inicio de sesion", "v0.1", "backend", "Como visitante quiero registrarme e iniciar sesion para tener mi cuenta."),
    @("H2 Buscar juegos", "v0.1", "backend", "Como usuario quiero buscar juegos por titulo, consola, genero y anio para encontrar lo que me interesa."),
    @("H3 Ficha de un juego", "v0.1", "backend", "Como usuario quiero ver la ficha de un juego (consola, anio, genero, caratula) para decidir si me interesa."),
    @("H4 Estado de un juego", "v0.1", "backend", "Como usuario quiero marcar un juego como Jugando, Proximo, Terminado o Abandonado para llevar mi registro."),
    @("H5 Calificacion y nota privada", "v0.1", "backend", "Como usuario quiero calificar un juego y escribir una nota privada para recordar que me parecio."),
    @("H6 Historial cronologico", "v0.1", "backend", "Como usuario quiero ver mi historial en orden cronologico para mirar atras lo que he jugado."),
    @("H7 Prioridad de pendientes", "v0.1", "backend", "Como usuario quiero asignar prioridad a los juegos de mi lista de pendientes para decidir que sigue."),
    @("H8 Dispositivos, emulador y rendimiento", "v0.1", "backend", "Como usuario quiero registrar mis dispositivos y anotar en cual y con que emulador jugue cada juego, y como corrio."),
    @("H9 Estadisticas personales", "v0.1", "backend", "Como usuario quiero ver estadisticas de mi actividad (por consola, por anio) para tener los pies en la tierra."),
    @("H10 Que juego ahora", "v0.1", "backend", "Como usuario quiero que me sugieran un juego de mi lista para dejar de dudar que jugar."),
    @("H11 Perfil publico o privado", "v0.2", "backend", "Como usuario quiero un perfil publico (con opcion de privado) para mostrar lo que he jugado."),
    @("H12 Resenas", "v0.2", "backend", "Como usuario quiero publicar resenas de juegos para compartir mi opinion."),
    @("H13 Listas tematicas", "v0.2", "backend", "Como usuario quiero crear listas tematicas para ayudar a otros."),
    @("H14 Seguir a otros", "v0.2", "backend", "Como usuario quiero seguir a otros y ver su actividad para descubrir juegos por gente que me gusta."),
    @("H15 Listas populares y curadas", "v0.3", "frontend", "Como novato quiero explorar listas populares y curadas para encontrar buenos juegos sin perderme."),
    @("H16 Juegos que corren bien en mi dispositivo", "v0.3", "backend", "Como usuario con un dispositivo quiero ver que juegos corren bien en el, segun otros usuarios."),
    @("H17 Vincular RetroAchievements", "v0.4", "backend", "Como usuario quiero vincular mi cuenta de RetroAchievements para importar mis juegos y logros."),
    @("H18 Progreso de logros", "v0.4", "backend", "Como usuario quiero ver mi progreso de logros por juego para saber cuanto me falta.")
)

$bodyFile = Join-Path $env:TEMP "rgl-issue-body.md"
$urls = @()
foreach ($i in $issues) {
    $body = "$($i[3])`n`n## Criterios de aceptacion`n`n- [ ] (por definir al empezar la historia)`n`n## Notas tecnicas`n`n(por definir)"
    Write-Utf8NoBom $bodyFile $body
    $url = gh issue create --repo $repo --title $i[0] --body-file $bodyFile --label $i[1] --label $i[2] --milestone $i[1]
    Assert-Ok "issue $($i[0])"
    $urls += $url
    Write-Host "Creado: $url"
}

# 5. Tablero (GitHub Projects) con los issues
$projectJson = gh project create --owner $owner --title "RetroGameLog" --format json | ConvertFrom-Json
Assert-Ok "crear el tablero"
foreach ($u in $urls) {
    gh project item-add $projectJson.number --owner $owner --url $u | Out-Null
    Assert-Ok "agregar $u al tablero"
}
Write-Host "Tablero creado: $($projectJson.url)"
