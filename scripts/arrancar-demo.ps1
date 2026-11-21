param(
    [ValidateRange(1024, 65535)][int]$PuertoPostgres = 55433,
    [ValidateRange(1024, 65535)][int]$PuertoWeb = 5000,
    [string]$PostgresBin = (Join-Path $env:ProgramFiles 'PostgreSQL\17\bin')
)

$ErrorActionPreference = 'Stop'
$proyecto = Split-Path -Parent $PSScriptRoot
$python = Join-Path $proyecto '.venv\Scripts\python.exe'
$pgCtl = Join-Path $PostgresBin 'pg_ctl.exe'
$initDb = Join-Path $PostgresBin 'initdb.exe'
$estado = Join-Path $proyecto '.local'
$datos = Join-Path $estado 'postgres-demo'
$claveDb = Join-Path $estado 'postgres-demo.password'
$logDb = Join-Path $estado 'postgres-demo.log'

function Ejecutar {
    param([string]$Programa, [string[]]$Argumentos)
    & $Programa @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "$(Split-Path -Leaf $Programa) devolvio el codigo $LASTEXITCODE."
    }
}

foreach ($archivo in @($python, (Join-Path $proyecto 'dist\index.html'), $pgCtl, $initDb)) {
    if (-not (Test-Path -LiteralPath $archivo -PathType Leaf)) {
        throw "Falta $archivo. Completa la preparación indicada en README.md."
    }
}

New-Item -ItemType Directory -Path $estado -Force | Out-Null
if (-not (Test-Path -LiteralPath $claveDb)) {
    if (Test-Path -LiteralPath (Join-Path $datos 'PG_VERSION')) {
        throw 'Falta la clave del PostgreSQL de demostración existente.'
    }
    $clave = & $python -c 'import secrets; print(secrets.token_hex(32))'
    if ($LASTEXITCODE -ne 0 -or -not $clave) {
        throw 'No se pudo generar la clave del PostgreSQL local.'
    }
    Set-Content -LiteralPath $claveDb -Value $clave -Encoding ascii
}

$clave = (Get-Content -LiteralPath $claveDb -Raw).Trim()
if ($clave -notmatch '^[a-f0-9]{64}$') {
    throw 'La clave local de PostgreSQL tiene un formato inesperado.'
}

if (-not (Test-Path -LiteralPath (Join-Path $datos 'PG_VERSION'))) {
    Ejecutar $initDb @('-D', $datos, '-U', 'glori', '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C', "--pwfile=$claveDb")
}

& $pgCtl -D $datos status | Out-Null
if ($LASTEXITCODE -ne 0) {
    Ejecutar $pgCtl @('-D', $datos, '-l', $logDb, '-o', "-h 127.0.0.1 -p $PuertoPostgres", '-w', 'start')
}
else {
    $puertoActivo = (Get-Content -LiteralPath (Join-Path $datos 'postmaster.pid'))[3]
    if ($puertoActivo -ne $PuertoPostgres) {
        throw "El PostgreSQL de Glori ya esta activo en el puerto $puertoActivo."
    }
}

Push-Location -LiteralPath $proyecto
try {
    $servidorDb = "postgresql://glori:${clave}@127.0.0.1:$PuertoPostgres"
    $env:DATABASE_URL = "$servidorDb/postgres"
    @'
import os
import psycopg

with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as db:
    exists = db.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("glori",)).fetchone()
    if not exists:
        db.execute("CREATE DATABASE glori")
'@ | & $python -B -
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo abrir o crear la base de Glori.'
    }
    $env:DATABASE_URL = "$servidorDb/glori"
    if (-not $env:GLORI_SECRET) {
        $env:GLORI_SECRET = & $python -c 'import secrets; print(secrets.token_hex(32))'
    }
    if (-not $env:GLORI_SECRET) {
        throw 'No se pudo generar la clave de sesion de Glori.'
    }
    Ejecutar $python @('-B', '-m', 'flask', '--app', 'glori', 'migrate')
    Ejecutar $python @('-B', '-m', 'flask', '--app', 'glori', 'seed-demo')
    $env:GLORI_SHOW_DEMO_ACCOUNTS = '1'
    Ejecutar $python @('-B', '-m', 'flask', '--app', 'glori', 'run', '--host', '127.0.0.1', '--port', "$PuertoWeb")
}
finally {
    Pop-Location
}
