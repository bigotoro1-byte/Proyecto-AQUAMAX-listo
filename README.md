# AQUAMAX PRO

Sistema de gestión de inventario para piscinas.

## 🚀 Instalación

pip install -r requirements.txt

## ▶️ Ejecutar

python app.py

## 💾 Backup Diario Gratis (GitHub Actions)

Se incluye el workflow `.github/workflows/backup-db.yml` para generar un respaldo diario de PostgreSQL en formato `.sql.gz`.

### Configuración necesaria

1. En GitHub, abre tu repositorio AQUAMAX.
2. Ve a **Settings > Secrets and variables > Actions**.
3. Crea el secret `DATABASE_URL` con la URL completa de tu PostgreSQL de Render.
4. Ve a **Actions** y ejecuta una vez el workflow **Backup PostgreSQL (Daily)** con **Run workflow** para probar.

### Dónde descargar el respaldo

1. En la ejecución del workflow, entra a la sección **Artifacts**.
2. Descarga el archivo `aquamax_backup_YYYYMMDD_HHMMSS.sql.gz`.

## 🌐 Funcionalidades

- Control de inventario
- Gestión de usuarios (roles)
- Reportes en PDF
- Control por ubicación

## 👨‍💻 Autor

Oscar Barreto
