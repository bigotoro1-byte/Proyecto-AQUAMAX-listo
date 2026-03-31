from flask import Blueprint, render_template, request, redirect, session, current_app
from database.db import conectar, actualizar_contrasena
from werkzeug.security import check_password_hash, generate_password_hash
import random
import string
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

auth_bp = Blueprint("auth", __name__)

FAILED_LOGINS = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def password_es_fuerte(password):
    if len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit


def _send_recovery_email(user, email, codigo):
    subject = 'Codigo de recuperacion AQUAMAX'
    body = (
        f'Hola {user},\n\n'
        f'Tu codigo de recuperacion es: {codigo}\n\n'
        'Este codigo expira en 15 minutos.\n\n'
        'Si no solicitaste esto, ignora este mensaje.'
    )

    # Envio por SMTP.
    mail_server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    mail_port = int(os.getenv('MAIL_PORT', 587))
    mail_user = os.getenv('MAIL_USERNAME')
    mail_pass = os.getenv('MAIL_PASSWORD')

    # Para Gmail, usar MAIL_USERNAME como remitente evita rechazo por sender distinto.
    smtp_from_env = (os.getenv('SMTP_FROM') or os.getenv('MAIL_FROM') or '').strip()
    if 'gmail' in (mail_server or '').lower() and mail_user:
        smtp_from = mail_user
    else:
        smtp_from = smtp_from_env or mail_user or 'no-reply@localhost'

    if not mail_user or not mail_pass:
        return False, 'SMTP sin credenciales'

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_from
        msg['To'] = email
        msg_text = MIMEText(body, 'plain', 'utf-8')
        msg.attach(msg_text)

        with smtplib.SMTP(mail_server, mail_port, timeout=8) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(mail_user, mail_pass)
            server.send_message(msg)
        return True, ''
    except Exception as e:
        current_app.logger.error(f'Error SMTP: {str(e)}')
        return False, f'SMTP: {str(e)}'


def _password_matches(expected_value, provided_password):
    if not expected_value or not provided_password:
        return False
    if expected_value.startswith(("pbkdf2:", "scrypt:")):
        try:
            return check_password_hash(expected_value, provided_password)
        except (ValueError, TypeError):
            return False
    return expected_value == provided_password


def _try_bootstrap_superadmin(user, password):
    env_user = (os.getenv('SUPERADMIN_USERNAME', 'superadmin') or '').strip()
    env_pass = (os.getenv('SUPERADMIN_PASSWORD', '') or '').strip()

    if not env_user or not env_pass:
        return None
    if (user or '').strip().lower() != env_user.lower():
        return None
    if not _password_matches(env_pass, password):
        return None

    hash_final = env_pass if env_pass.startswith(("pbkdf2:", "scrypt:")) else generate_password_hash(env_pass)

    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM usuarios WHERE LOWER(username) = LOWER(%s)", (env_user,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE usuarios SET password = %s, rol = 'superadmin' WHERE LOWER(username) = LOWER(%s)",
                (hash_final, env_user)
            )
            username_real = row[0]
        else:
            cursor.execute(
                "INSERT INTO usuarios (username, password, rol) VALUES (%s, %s, 'superadmin')",
                (env_user, hash_final)
            )
            username_real = env_user
        conn.commit()
        return (username_real, hash_final, 'superadmin')
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"No se pudo bootstrapear superadmin: {str(e)}")
        return None
    finally:
        conn.close()

@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        user = (request.form.get("user") or '').strip()
        password = request.form.get("password")

        if not user or not password:
            return render_template("login.html", error="Completa todos los campos")

        key = (user or "").strip().lower()
        state = FAILED_LOGINS.get(key, {"count": 0, "until": 0})
        now = time.time()
        if state.get("until", 0) > now:
            wait = int(state["until"] - now)
            return render_template("login.html", error=f"Cuenta bloqueada temporalmente. Intenta en {wait}s")

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE LOWER(username) = LOWER(%s)", (user,))
        usuario = cursor.fetchone()

        conn.close()

        password_ok = False
        if usuario:
            try:
                password_ok = check_password_hash(usuario[1], password)
            except (ValueError, TypeError):
                current_app.logger.error(f"Hash invalido para usuario: {user}")

        if not (usuario and password_ok):
            usuario_bootstrap = _try_bootstrap_superadmin(user, password)
            if usuario_bootstrap:
                usuario = usuario_bootstrap
                password_ok = True

        if usuario and password_ok:
            FAILED_LOGINS.pop(key, None)
            session["user"] = usuario[0]
            session["rol"] = usuario[2]
            # Detectar contraseña débil/default y forzar cambio
            passwords_debiles = ["1234", "admin", "password", "aquamax", "123456", "1234abcd"]
            es_debil = any(
                check_password_hash(usuario[1], pw)
                for pw in passwords_debiles
            )
            if es_debil:
                session["debe_cambiar_password"] = True
            return redirect("/dashboard")

        # Incrementar intentos fallidos
        state["count"] = state.get("count", 0) + 1
        if state["count"] >= MAX_LOGIN_ATTEMPTS:
            state["until"] = now + LOCKOUT_SECONDS
            state["count"] = 0
        FAILED_LOGINS[key] = state

        current_app.logger.warning(f"Login fallido: user={user}, exists={bool(usuario)}")

        # Mensaje de error simplificado (producción seguro)
        if not usuario:
            error_message = "Credenciales incorrectas"
        else:
            error_message = "Credenciales incorrectas"
            # En modo depuración solo para admin puedes añadir contexto:
            if usuario[2] == "admin":
                error_message = "Credenciales incorrectas. Si eres admin y no recuerdas tu contraseña, restaura tu .env"

        return render_template("login.html", error=error_message)

    if session.get("user"):
        return redirect("/dashboard")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@auth_bp.route('/cambiar_contrasena', methods=['GET', 'POST'])
def cambiar_contrasena():
    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':
        actual = request.form.get('actual')
        nueva = request.form.get('nueva')
        confirmar = request.form.get('confirmar')

        if not actual or not nueva or not confirmar:
            return render_template('cambiar_contrasena.html', error='Completa todos los campos')

        if nueva != confirmar:
            return render_template('cambiar_contrasena.html', error='Las contraseñas no coinciden')

        if not password_es_fuerte(nueva):
            return render_template('cambiar_contrasena.html', error='La contraseña debe tener al menos 8 caracteres, letras y numeros')

        conn = conectar()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM usuarios WHERE username = %s', (session['user'],))
        usuario = cursor.fetchone()
        conn.close()

        password_ok = False
        if usuario:
            try:
                password_ok = check_password_hash(usuario[0], actual)
            except (ValueError, TypeError):
                current_app.logger.error(f"Hash invalido en cambio de clave para usuario: {session.get('user')}")

        if not usuario or not password_ok:
            return render_template('cambiar_contrasena.html', error='Contraseña actual incorrecta')

        actualizar_contrasena(session['user'], generate_password_hash(nueva))
        session.pop('debe_cambiar_password', None)
        return render_template('cambiar_contrasena.html', success='Contraseña actualizada correctamente')

    forzado = session.get('debe_cambiar_password', False)
    return render_template('cambiar_contrasena.html', forzado=forzado)


@auth_bp.route('/recuperar_contrasena', methods=['GET', 'POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        step = request.form.get('step', '1')

        if step == '1':
            # Paso 1: Usuario solicita código
            user = (request.form.get('user') or '').strip()
            mode = (request.form.get('mode') or 'email').strip().lower()
            email = (request.form.get('email') or '').strip()

            if not user:
                return render_template('recuperar_contrasena.html', error='Completa el usuario', step=1)

            if mode != 'master' and not email:
                return render_template('recuperar_contrasena.html', error='Completa usuario y correo', step=1)

            try:
                conn = conectar()
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM usuarios WHERE LOWER(username) = LOWER(%s)', (user,))
                usuario = cursor.fetchone()
                conn.close()
            except Exception as e:
                current_app.logger.error(f'Error consultando usuario para recuperacion: {str(e)}')
                return render_template(
                    'recuperar_contrasena.html',
                    error='Sistema ocupado temporalmente. Intenta nuevamente en unos segundos.',
                    step=1
                )

            if not usuario:
                return render_template('recuperar_contrasena.html', error='Usuario no existe', step=1)

            # Generar código de 6 dígitos
            codigo = ''.join(random.choices(string.digits, k=6))
            session['recovery_user'] = user
            session['recovery_code'] = codigo
            session['recovery_email'] = email
            session['recovery_code_time'] = datetime.now().timestamp()
            session['recovery_mode_master'] = (mode == 'master')
            session.pop('recovery_send_error', None)

            if mode == 'master':
                session['recovery_attempts'] = 0
                session['recovery_email_failed'] = False
                return render_template(
                    'recuperar_contrasena.html',
                    success='Modo codigo maestro activado. Ingresa el codigo maestro y tu nueva contraseña.',
                    step=2
                )

            # Enviar email con el código (Resend principal, SMTP fallback)
            sent, envio_detalle = _send_recovery_email(user, email, codigo)
            session['recovery_attempts'] = 0
            if sent:
                session['recovery_email_failed'] = False
                session['recovery_mode_master'] = False
                return render_template('recuperar_contrasena.html', success='Se envio un codigo a tu correo', step=2)

            session['recovery_email_failed'] = True
            session['recovery_mode_master'] = False
            session['recovery_send_error'] = (envio_detalle or 'Error no especificado')[:200]
            return render_template(
                'recuperar_contrasena.html',
                error='No se pudo enviar correo. Usa el codigo maestro de recuperacion.',
                step=2,
                envio_detalle=session.get('recovery_send_error')
            )

        elif step == '2':
            # Paso 2: Usuario ingresa código y nueva contraseña
            codigo = (request.form.get('codigo') or '').strip()
            nueva = request.form.get('nueva')
            confirmar = request.form.get('confirmar')

            if not session.get('recovery_user'):
                return render_template('recuperar_contrasena.html', error='Sesión expirada', step=1)

            ts = session.get('recovery_code_time', 0)
            if (time.time() - ts) > 900:
                session.pop('recovery_user', None)
                session.pop('recovery_code', None)
                session.pop('recovery_attempts', None)
                session.pop('recovery_send_error', None)
                session.pop('recovery_mode_master', None)
                return render_template('recuperar_contrasena.html', error='El codigo expiro. Solicita uno nuevo.', step=1)

            if not codigo or not nueva or not confirmar:
                return render_template('recuperar_contrasena.html', error='Completa todos los campos', step=2)

            recovery_master = (os.getenv('RECOVERY_CODE') or '').strip()
            codigo_valido = (codigo == session.get('recovery_code')) or (recovery_master and codigo == recovery_master)

            if not codigo_valido:
                session['recovery_attempts'] = session.get('recovery_attempts', 0) + 1
                if session['recovery_attempts'] >= 5:
                    session.pop('recovery_user', None)
                    session.pop('recovery_code', None)
                    session.pop('recovery_attempts', None)
                    session.pop('recovery_email_failed', None)
                    session.pop('recovery_send_error', None)
                    session.pop('recovery_mode_master', None)
                    return render_template('recuperar_contrasena.html', error='Demasiados intentos. Solicita un nuevo codigo.', step=1)
                return render_template('recuperar_contrasena.html', error='Código incorrecto', step=2)

            if nueva != confirmar:
                return render_template('recuperar_contrasena.html', error='Las contraseñas no coinciden', step=2)

            if not password_es_fuerte(nueva):
                return render_template('recuperar_contrasena.html', error='La contraseña debe tener al menos 8 caracteres, letras y numeros', step=2)

            # Actualizar contraseña
            try:
                actualizar_contrasena(session['recovery_user'], generate_password_hash(nueva))
            except Exception as e:
                current_app.logger.error(f'Error actualizando contraseña por recuperacion: {str(e)}')
                return render_template('recuperar_contrasena.html', error='No se pudo actualizar la contraseña. Intenta nuevamente.', step=2)
            session.pop('recovery_user', None)
            session.pop('recovery_code', None)
            session.pop('recovery_attempts', None)
            session.pop('recovery_email_failed', None)
            session.pop('recovery_send_error', None)
            session.pop('recovery_mode_master', None)

            return render_template('recuperar_contrasena.html', success='Contraseña actualizada. Ya puedes iniciar sesión', step=1)

    return render_template('recuperar_contrasena.html', step=1)