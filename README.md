# Glori

Aplicación académica de ventas al crédito, cuentas corrientes y cobranzas. Ejecución local en Windows con React, Flask y PostgreSQL.

## Arranque en PowerShell

Instala Python 3.12, Node.js 22 y PostgreSQL 17. Si PowerShell abre el alias de Microsoft Store al ejecutar `python`, usa la ruta del Python instalado (por ejemplo, `$env:LOCALAPPDATA\Programs\Python\Python312\python.exe`). Instala dependencias y compila la interfaz una vez.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
npm.cmd run build
```

Para arrancar la demo desde la carpeta del proyecto, ejecuta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\arrancar-demo.ps1
```

El script crea o reutiliza el PostgreSQL de demostración en `.local\postgres-demo`, puerto `55433`, y aplica las migraciones antes de iniciar Flask. Usa `-PostgresBin` si PostgreSQL está instalado en otra carpeta. Abre [Glori local](http://127.0.0.1:5000). Si el puerto web está ocupado, agrega `-PuertoWeb 5001` y abre [Glori en el puerto 5001](http://127.0.0.1:5001).

La contraseña de los usuarios ficticios de la aplicación es `Glori-demo-2026`. El script genera su propia contraseña de base de datos.

En la pantalla de acceso, **Entrar a Bodegas Gloria** abre el panel operativo que corresponde al mockup. **Gestionar tiendas** abre la administración global y **Ver mi cuenta** abre el portal del cliente. Los tres perfiles también admiten inicio de sesión manual.

| Perfil | Usuario |
|---|---|
| Plataforma | `demo.plataforma` |
| Bodegas Gloria | `gloria.admin` |
| Cliente de Bodegas Gloria | `gloria.cliente` |
| Panadería del Barrio | `panaderia.admin` |
| Cliente de Panadería del Barrio | `panaderia.cliente` |

## Publicación desde GitHub

1. Crea un repositorio privado vacío en GitHub y copia su URL HTTPS. En PowerShell, desde `Proyecto_Glori`, ejecuta:

   ```powershell
   git init -b main
   git add .
   git status --short
   git commit -m "Publicación inicial de Glori"
   git remote add origin https://github.com/TU-USUARIO/glori.git
   git push -u origin main
   ```

   Sustituye `TU-USUARIO/glori` por tu repositorio. Antes de confirmar, revisa que `.local`, `.venv`, `.env`, `node_modules` y archivos de base de datos queden fuera. [Guía oficial de GitHub para Windows](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github?platform=windows)

2. En Render, selecciona **New → Blueprint** y conecta el repo. El archivo `render.yaml` declara el servicio y su base PostgreSQL. Cuando Render pida `GLORI_ADMIN_PASSWORD`, usa una clave nueva de 8 a 128 caracteres. Render genera la clave de sesión y entrega la URL de la base al servicio. [Guía de Blueprints de Render](https://render.com/docs/infrastructure-as-code)
3. Abre la URL que dé Render e inicia sesión como `admin` con la clave que configuraste. Crea una tienda en **Tiendas**, con su propio administrador y contraseña. Cambia de cuenta e ingresa con ese usuario. Desde el panel de la tienda carga el catálogo y los clientes, y prueba una venta y un cobro. La base web comienza vacía, con el administrador inicial. La base y las credenciales de demostración locales se quedan en tu equipo.

El Blueprint configura una demo temporal con el plan gratuito. Para preservar los datos por más de 30 días, selecciona un plan persistente de PostgreSQL. Si el cierre debe ejecutarse sin una consulta en la web, agrega un **Cron Job** en Render desde el mismo repositorio, con runtime Docker, comando `python -m flask --app glori close-cycles` y horario `* * * * *`. Usa la misma base interna y configura `GLORI_SECRET` en el Cron Job. La consulta de cada cuenta también procesa sus cortes pendientes. [Límites del plan gratuito](https://render.com/docs/free) · [Programación y costo del Cron Job](https://render.com/docs/cronjobs)

### Usar otra base PostgreSQL

Configura `DATABASE_URL` con la conexión real de una base ya creada y `GLORI_SECRET` con una clave de sesión. Desde PowerShell, ejecuta `.\.venv\Scripts\python.exe -m flask --app glori migrate` y comprueba que finalice correctamente. En una base de demostración puedes ejecutar `seed-demo`. Inicia el servidor con `.\.venv\Scripts\python.exe -m flask --app glori run --host 127.0.0.1`.

## Cortes y demostración

En una segunda terminal, con las mismas variables de conexión, inicia el proceso de corte. Revisa los ciclos cada 15 segundos y recupera cortes pendientes al volver a arrancar. La consulta de cuenta también genera los cortes pendientes de ese cliente.

```powershell
.\.venv\Scripts\python.exe -m flask --app glori close-cycles --watch
```

Para reproducir las fechas de septiembre, usa una base de demostración, detén el proceso de corte programado y establece `$env:GLORI_DEMO_DATES = '1'` antes de arrancar Flask. Los formularios de venta y cobranza mostrarán un campo de fecha ISO con desplazamiento de zona horaria. Registra todas las compras del ejercicio antes de consultar un corte posterior. Una vez emitido el estado, se rechaza registrar una compra retroactiva en ese ciclo.

Consulta el [guion, modelo y casos de aceptación](docs/evidencia.md) y el [registro de apoyo de IA](USO_IA.md).

## Pruebas

En otra sesión de PowerShell configura las mismas variables y usa una base local de prueba migrada con datos ficticios. Detén Flask y el proceso de corte para ejecutar Playwright, que inicia su propio servidor, requiere Microsoft Edge y registra operaciones de prueba. Las pruebas de integración de Python usan un esquema temporal.

```powershell
$env:GLORI_TEST_DATABASE_URL = $env:DATABASE_URL
.\.venv\Scripts\python.exe -B -m unittest -v
$env:GLORI_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
npm.cmd run test:e2e
```
