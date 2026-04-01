from flask import Flask, session, redirect, flash
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from database.db import crear_tablas, actualizar_tabla, insert_usuario, get_usuario, cerrar_acceso_login, get_revocacion_usuario, acceso_esta_revocado
from werkzeug.security import generate_password_hash
import os
import time
from datetime import timedelta
from dotenv import load_dotenv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.inventario import inventario_bp
from routes.productos import productos_bp
from routes.usuarios import usuarios_bp

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    raise RuntimeError('SECRET_KEY no está configurado en .env. Define SECRET_KEY y reinicia la aplicación.')
app.secret_key = secret_key
is_development = os.getenv('FLASK_ENV', '').strip().lower() == 'development'
allow_weak_defaults = os.getenv('ALLOW_WEAK_DEFAULTS', 'false').strip().lower() == 'true' or is_development

# Cierre automatico de sesion por inactividad (minutos)
session_timeout_minutes = int(os.getenv('SESSION_TIMEOUT_MINUTES', '6'))
if session_timeout_minutes < 5:
    session_timeout_minutes = 5
app.config['SESSION_TIMEOUT_SECONDS'] = session_timeout_minutes * 60
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=app.config['SESSION_TIMEOUT_SECONDS'])

# Habilitar CSRF (requerido) y evitar evaluación insegura
app.config['WTF_CSRF_ENABLED'] = True
csrf = CSRFProtect(app)

# 🔒 Hardening de cookies HTTP
app.config['SESSION_COOKIE_SECURE'] = not is_development  # HTTPS only (no en desarrollo)
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No accesible desde JavaScript (previene XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Previene ataques CSRF

# Caché de archivos estáticos (CSS, JS, imágenes)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000

# 📧 Configurar Flask-Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_FROM', 'aquamax@tuempresa.com')
app.config['MAIL_ASCII_ATTACHMENTS'] = False

mail = Mail(app)


@app.before_request
def controlar_sesion_por_inactividad():
    if not session.get('user'):
        return None

    # Cierre forzado en tiempo real: por acceso específico o por usuario.
    try:
        acceso_id = session.get('acceso_login_id')
        if acceso_id and acceso_esta_revocado(acceso_id):
            try:
                cerrar_acceso_login(acceso_id)
            except Exception:
                pass
            session.clear()
            flash('Tu sesion fue cerrada por un administrador.', 'error')
            return redirect('/login')

        usuario = session.get('user')
        revoked_at = get_revocacion_usuario(usuario)
        login_at_ts = int(session.get('login_at_ts') or 0)
        if revoked_at and ((not login_at_ts) or revoked_at.timestamp() >= login_at_ts):
            if acceso_id:
                try:
                    cerrar_acceso_login(acceso_id)
                except Exception:
                    pass
            session.clear()
            flash('Tu sesion fue cerrada por un administrador.', 'error')
            return redirect('/login')
    except Exception:
        # Si falla la verificacion de revocacion no debe romper la app.
        pass

    now_ts = int(time.time())
    last_activity = session.get('last_activity_ts')
    timeout_seconds = int(app.config.get('SESSION_TIMEOUT_SECONDS', 1800))

    if last_activity and (now_ts - int(last_activity)) > timeout_seconds:
        acceso_id = session.get('acceso_login_id')
        if acceso_id:
            try:
                cerrar_acceso_login(acceso_id)
            except Exception:
                pass
        session.clear()
        flash('Tu sesion caduco por inactividad. Inicia sesion nuevamente.', 'error')
        return redirect('/login')

    session['last_activity_ts'] = now_ts
    session.modified = True
    return None


@app.context_processor
def inyectar_datos_sesion():
    tz_co = ZoneInfo('America/Bogota')

    def fmt_dt_co(value):
        if not value:
            return '-'
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                txt = str(value).strip()
                dt = None
                try:
                    dt = datetime.fromisoformat(txt)
                except ValueError:
                    pass
                if dt is None:
                    try:
                        dt = datetime.strptime(txt, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        return txt

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(tz_co).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(value)

    return {
        'session_timeout_seconds': int(app.config.get('SESSION_TIMEOUT_SECONDS', 1800)),
        'session_login_ts': session.get('login_at_ts'),
        'session_last_activity_ts': session.get('last_activity_ts'),
        'fmt_dt_co': fmt_dt_co,
    }

# 🔌 DB
crear_tablas()
actualizar_tabla()

# 🔐 CREAR ADMIN AUTOMÁTICO
def crear_admin():
    admin_username = os.getenv('ADMIN_USERNAME', 'admin').strip() or 'admin'
    admin_password_plain = (os.getenv('ADMIN_PASSWORD') or '').strip()

    # Si la variable no se ha definido/actualizado en .env
    if not admin_password_plain or admin_password_plain.lower() == 'hashed_password_here':
        if allow_weak_defaults:
            admin_password_plain = '1234'
        else:
            admin_password_plain = None
            print('ADMIN_PASSWORD no configurado. Se omite creación automática de admin por seguridad.')

    if admin_password_plain:
        # Si viene un hash preconstruido, no volverlo a hashear
        if admin_password_plain.startswith(('pbkdf2:', 'scrypt:')):
            password = admin_password_plain
        else:
            password = generate_password_hash(admin_password_plain)

        # Admin seguro (no reescribir en cada arranque)
        try:
            if not get_usuario(admin_username):
                insert_usuario(admin_username, password, "admin")
        except Exception as e:
            print("Error creando admin:", e)

    # Usuario de prueba
    create_test_user = os.getenv('CREATE_TEST_USER', 'false').strip().lower() == 'true'
    if create_test_user:
        try:
            if not get_usuario("testuser"):
                insert_usuario("testuser", generate_password_hash("1234"), "user")
        except Exception as e:
            print("Error creando testuser:", e)

    # Super administrador del sistema
    superadmin_username = os.getenv('SUPERADMIN_USERNAME', 'superadmin').strip() or 'superadmin'
    superadmin_password_plain = (os.getenv('SUPERADMIN_PASSWORD') or '').strip()
    if not superadmin_password_plain:
        if allow_weak_defaults:
            superadmin_password_plain = '1234'
        else:
            print('SUPERADMIN_PASSWORD no configurado. Se omite creación automática de superadmin por seguridad.')

    if superadmin_password_plain:
        if superadmin_password_plain.startswith(('pbkdf2:', 'scrypt:')):
            superadmin_password = superadmin_password_plain
        else:
            superadmin_password = generate_password_hash(superadmin_password_plain)

        try:
            if not get_usuario(superadmin_username):
                insert_usuario(superadmin_username, superadmin_password, "superadmin")
        except Exception as e:
            print("Error creando superadmin:", e)

crear_admin()

# 🔗 RUTAS
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(inventario_bp)
app.register_blueprint(productos_bp)
app.register_blueprint(usuarios_bp)
if os.getenv("SHOW_ROUTES", "false").lower() == "true":
    print(app.url_map)

# 🚀 RUN
if __name__ == "__main__":
    debug_mode = os.getenv('FLASK_DEBUG', 'false').strip().lower() == 'true'
    app.run(debug=debug_mode, port=int(os.getenv('PORT', '5001')))