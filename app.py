from flask import Flask
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from database.db import crear_tablas, actualizar_tabla, insert_usuario, get_usuario
from werkzeug.security import generate_password_hash
import os
from dotenv import load_dotenv

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

# Habilitar CSRF (requerido) y evitar evaluación insegura
app.config['WTF_CSRF_ENABLED'] = True
csrf = CSRFProtect(app)

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

# 🔌 DB
crear_tablas()
actualizar_tabla()

# 🔐 CREAR ADMIN AUTOMÁTICO
def crear_admin():
    admin_username = os.getenv('ADMIN_USERNAME', 'admin').strip() or 'admin'
    admin_password_plain = os.getenv('ADMIN_PASSWORD', '1234').strip()

    # Si la variable no se ha definido/actualizado en .env
    if not admin_password_plain or admin_password_plain.lower() == 'hashed_password_here':
        admin_password_plain = '1234'

    # Si viene un hash preconstruido, no lo volverse a hashear
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
    try:
        if not get_usuario("testuser"):
            insert_usuario("testuser", generate_password_hash("1234"), "user")
    except Exception as e:
        print("Error creando testuser:", e)

    # Super administrador del sistema
    superadmin_username = os.getenv('SUPERADMIN_USERNAME', 'superadmin').strip() or 'superadmin'
    superadmin_password_plain = os.getenv('SUPERADMIN_PASSWORD', '1234').strip() or '1234'
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
    app.run(debug=True, port=5001)