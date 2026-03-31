from flask import Blueprint, render_template, request, redirect, session, flash, send_file
from database.db import conectar, get_configuracion_stock, set_configuracion_stock, get_configuracion_stock_productos_en_stock, set_configuracion_stock_producto, get_ubicaciones, add_ubicacion, delete_ubicacion, get_accesos_login, registrar_evento_sistema, get_panel_salud, registrar_accion_admin, limpiar_datos_expirados, get_auditoria, get_alertas_condiciones, get_usuarios_admin_email
from werkzeug.security import generate_password_hash
from datetime import datetime
import os
import shutil
import re
import io
from openpyxl import Workbook

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/admin")


def _append_table_sheet(cursor, wb, table_name):
    ws = wb.create_sheet(title=table_name[:31])
    columnas_excluidas = {
        "usuarios": {"password"},
        "password_recovery_state": {"codigo", "codigo_hash"},
    }

    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    columnas = [r[0] for r in cursor.fetchall()]
    columnas = [c for c in columnas if c not in columnas_excluidas.get(table_name, set())]

    if not columnas:
        ws.append(["sin_columnas"])
        return

    columnas_sql = ", ".join(f'"{c}"' for c in columnas)
    cursor.execute(f'SELECT {columnas_sql} FROM "{table_name}"')
    rows = cursor.fetchall()
    headers = list(columnas)

    if headers:
        ws.append(headers)

    for row in rows:
        ws.append(list(row))


def _generar_excel_db():
    conn = conectar()
    cursor = conn.cursor()
    try:
        wb = Workbook()
        # Elimina la hoja por defecto para dejar solo tablas reales.
        wb.remove(wb.active)

        tablas = [
            "usuarios",
            "productos",
            "inventario",
            "movimientos",
            "configuracion",
            "configuracion_producto",
            "ubicaciones",
            "accesos_login",
            "auth_login_state",
            "password_recovery_state",
        ]

        for tabla in tablas:
            _append_table_sheet(cursor, wb, tabla)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
    finally:
        conn.close()


def password_es_fuerte(password):
    if not password or len(password) < 8:
        return False
    return bool(re.search(r"[A-Za-z]", password) and re.search(r"\d", password))


def email_valido(email):
    if not email:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


# 🔐 LISTAR Y CREAR USUARIOS
@usuarios_bp.route("/usuarios", methods=["GET", "POST"])
def usuarios():

    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    conn = conectar()
    cursor = conn.cursor()

    # 👉 CREAR USUARIO
    if request.method == "POST":
        user = request.form.get("usuario")
        password = request.form.get("password")
        rol = request.form.get("rol")
        email = (request.form.get("email") or "").strip().lower()

        if not user or not password or not rol or not email:
            return render_template("usuarios.html", error="Completa todos los campos")

        if not email_valido(email):
            return render_template("usuarios.html", error="Ingresa un correo valido")

        if not password_es_fuerte(password):
            return render_template("usuarios.html", error="La contraseña debe tener al menos 8 caracteres, letras y numeros")

        if rol == "superadmin" and session.get("rol") != "superadmin":
            return render_template("usuarios.html", error="Solo superadmin puede crear otro superadmin")

        cursor.execute("SELECT 1 FROM usuarios WHERE LOWER(email) = LOWER(%s)", (email,))
        if cursor.fetchone():
            return render_template("usuarios.html", error="Ese correo ya esta asignado a otro usuario")

        try:
            cursor.execute(
                "INSERT INTO usuarios (username, password, rol, email) VALUES (%s, %s, %s, %s)",
                (user, generate_password_hash(password), rol, email)
            )
            conn.commit()
            # 🔐 Auditoría: registrar creación de usuario
            registrar_accion_admin(
                accion='crear_usuario',
                username=session.get('username', 'desconocido'),
                estado='ok',
                detalle=f'Usuario: {user}, Rol: {rol}, Email: {email}',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')
            )
        except Exception as e:
            # 🔐 Auditoría: registrar fallo en creación de usuario
            registrar_accion_admin(
                accion='crear_usuario',
                username=session.get('username', 'desconocido'),
                estado='error',
                detalle=f'Intento fallido: {str(e)}',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')
            )
            return render_template("usuarios.html", error="Usuario o correo ya existe")

    # 👉 LISTAR
    cursor.execute("SELECT * FROM usuarios")
    lista = cursor.fetchall()

    conn.close()

    return render_template("usuarios.html", usuarios=lista)


# 🗑️ ELIMINAR USUARIO
@usuarios_bp.route("/usuarios/eliminar/<user>", methods=["POST"])
def eliminar_usuario(user):

    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    if user in ("admin", "superadmin"):
        flash("No puedes eliminar usuarios protegidos", "error")
        # 🔐 Auditoría: intento no autorizado
        registrar_accion_admin(
            accion='eliminar_usuario',
            username=session.get('username', 'desconocido'),
            estado='error',
            detalle=f'Intento de eliminar usuario protegido: {user}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        return redirect("/admin/usuarios")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM usuarios WHERE username=%s", (user,))
    conn.commit()
    conn.close()

    # 🔐 Auditoría: eliminación exitosa
    registrar_accion_admin(
        accion='eliminar_usuario',
        username=session.get('username', 'desconocido'),
        estado='ok',
        detalle=f'Usuario eliminado: {user}',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')
    )

    return redirect("/admin/usuarios")


@usuarios_bp.route("/usuarios/actualizar_email/<user>", methods=["POST"])
def actualizar_email_usuario(user):
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    nuevo_email = (request.form.get("email") or "").strip().lower()
    if not email_valido(nuevo_email):
        flash("Correo invalido", "error")
        return redirect("/admin/usuarios")

    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM usuarios WHERE LOWER(email) = LOWER(%s) AND LOWER(username) <> LOWER(%s)",
            (nuevo_email, user),
        )
        if cursor.fetchone():
            flash("Ese correo ya esta asignado a otro usuario", "error")
            return redirect("/admin/usuarios")

        cursor.execute("UPDATE usuarios SET email=%s WHERE username=%s", (nuevo_email, user))
        conn.commit()
        flash("Correo actualizado correctamente", "success")
    except Exception as e:
        conn.rollback()
        flash(f"No se pudo actualizar el correo: {str(e)}", "error")
    finally:
        conn.close()

    return redirect("/admin/usuarios")


def _crear_respaldo_db():
    # Con PostgreSQL el backup de archivo local no aplica.
    # El respaldo se gestiona desde el panel de Render (PostgreSQL Backups).
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"backup_postgres_{stamp} (gestionado por Render)"


@usuarios_bp.route("/exportar-db-xlsx", methods=["GET"])
def exportar_db_xlsx():
    if "rol" not in session or session["rol"] != "superadmin":
        return render_template("acceso_denegado.html"), 403

    try:
        excel_buffer = _generar_excel_db()
    except Exception as e:
        try:
            registrar_evento_sistema('export_db_xlsx', 'error', f'Fallo exportacion: {str(e)[:220]}', session.get('user'))
            registrar_accion_admin(
                accion='exportar_db_xlsx',
                username=session.get('username', 'desconocido'),
                estado='error',
                detalle=str(e)[:220],
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')
            )
        except Exception:
            pass
        flash(f"No se pudo generar el archivo Excel: {str(e)}", "error")
        return redirect("/admin/sistema")

    nombre = f"aquamax_db_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        registrar_evento_sistema('export_db_xlsx', 'ok', f'Archivo: {nombre}', session.get('user'))
        registrar_accion_admin(
            accion='exportar_db_xlsx',
            username=session.get('username', 'desconocido'),
            estado='ok',
            detalle=f'Archivo: {nombre}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
    except Exception:
        pass
    return send_file(
        excel_buffer,
        as_attachment=True,
        download_name=nombre,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@usuarios_bp.route('/salud')
def salud_sistema():
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    try:
        salud = get_panel_salud(limit_emails=12)
    except Exception as e:
        flash(f"No se pudo cargar el panel de salud: {str(e)}", "error")
        salud = {
            'db_size_bytes': 0,
            'sesiones_activas': 0,
            'fallos_24h': 0,
            'bloqueos_activos': 0,
            'ultimo_backup': None,
            'ultimo_email': None,
            'emails_recientes': [],
        }

    bytes_val = int(salud.get('db_size_bytes') or 0)
    if bytes_val < 1024:
        db_size = f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        db_size = f"{bytes_val / 1024:.2f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        db_size = f"{bytes_val / (1024 * 1024):.2f} MB"
    else:
        db_size = f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"

    return render_template('salud_sistema.html', salud=salud, db_size=db_size)


@usuarios_bp.route("/sistema", methods=["GET", "POST"])
def sistema():
    if "rol" not in session or session["rol"] != "superadmin":
        return render_template("acceso_denegado.html"), 403

    if request.method == "POST":
        action = request.form.get("action")
        confirm = (request.form.get("confirm", "") or "").strip().upper()

        try:
            backup_path = _crear_respaldo_db()
        except Exception as e:
            flash(f"No se pudo crear respaldo: {str(e)}", "error")
            return redirect("/admin/sistema")

        conn = conectar()
        cursor = conn.cursor()

        try:
            if action == "limpiar_inventario":
                if confirm != "LIMPIAR":
                    flash("Confirmacion invalida. Escribe LIMPIAR.", "error")
                    return redirect("/admin/sistema")

                cursor.execute("DELETE FROM inventario")
                conn.commit()
                registrar_accion_admin(
                    accion='limpiar_inventario',
                    username=session.get('username', 'desconocido'),
                    estado='ok',
                    detalle=f'Inventario limpiado. Respaldo: {backup_path}',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                flash(f"Inventario limpiado. Respaldo: {backup_path}", "success")

            elif action == "reiniciar_datos":
                if confirm != "REINICIAR":
                    flash("Confirmacion invalida. Escribe REINICIAR.", "error")
                    return redirect("/admin/sistema")

                cursor.execute("DELETE FROM inventario")
                cursor.execute("DELETE FROM productos")
                cursor.execute("DELETE FROM usuarios WHERE rol NOT IN ('admin', 'superadmin')")
                conn.commit()
                registrar_accion_admin(
                    accion='reiniciar_datos',
                    username=session.get('username', 'desconocido'),
                    estado='ok',
                    detalle=f'Datos del sistema reiniciados. Respaldo: {backup_path}',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                flash(f"Datos reiniciados correctamente. Respaldo: {backup_path}", "success")

            else:
                flash("Accion no valida", "error")

        except Exception as e:
            conn.rollback()
            flash(f"Error ejecutando accion: {str(e)}", "error")
        finally:
            conn.close()

        return redirect("/admin/sistema")

    return render_template("sistema.html")


@usuarios_bp.route("/ajustes-stock", methods=["GET", "POST"])
def ajustes_stock():
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    if request.method == "POST":
        try:
            min_entrada = float(request.form.get("min_cantidad_entrada", "0.01"))
            min_salida = float(request.form.get("min_cantidad_salida", "0.01"))
            umbral_critico = float(request.form.get("umbral_critico", "5"))
            umbral_medio = float(request.form.get("umbral_medio", "15"))
            umbral_alerta_dashboard = float(request.form.get("umbral_alerta_dashboard", "10"))
        except ValueError:
            flash("Valores invalidos. Usa solo numeros.", "error")
            return redirect("/admin/ajustes-stock")

        if min_entrada <= 0 or min_salida <= 0:
            flash("Los minimos deben ser mayores a 0.", "error")
            return redirect("/admin/ajustes-stock")

        if umbral_critico < 0 or umbral_medio < 0 or umbral_alerta_dashboard < 0:
            flash("Los umbrales no pueden ser negativos.", "error")
            return redirect("/admin/ajustes-stock")

        if umbral_critico > umbral_medio:
            flash("El umbral critico no puede ser mayor que el umbral medio.", "error")
            return redirect("/admin/ajustes-stock")

        set_configuracion_stock({
            "min_cantidad_entrada": min_entrada,
            "min_cantidad_salida": min_salida,
            "umbral_critico": umbral_critico,
            "umbral_medio": umbral_medio,
            "umbral_alerta_dashboard": umbral_alerta_dashboard,
        })

        # Guardar ajustes por producto en stock
        productos_en_stock = get_configuracion_stock_productos_en_stock()
        for p in productos_en_stock:
            pid = p[0]
            try:
                p_critico = float(request.form.get(f"umbral_critico__{pid}", str(umbral_critico)))
                p_medio = float(request.form.get(f"umbral_medio__{pid}", str(umbral_medio)))
                p_alerta = float(request.form.get(f"umbral_alerta_dashboard__{pid}", str(umbral_alerta_dashboard)))
            except ValueError:
                flash(f"Valor invalido en producto {p[1]}", "error")
                return redirect("/admin/ajustes-stock")

            if p_critico < 0 or p_medio < 0 or p_alerta < 0:
                flash(f"Umbrales negativos no permitidos en {p[1]}", "error")
                return redirect("/admin/ajustes-stock")
            if p_critico > p_medio:
                flash(f"El umbral critico no puede ser mayor al medio en {p[1]}", "error")
                return redirect("/admin/ajustes-stock")

            set_configuracion_stock_producto(pid, p_critico, p_medio, p_alerta)

        flash("Ajustes de stock actualizados correctamente.", "success")
        return redirect("/admin/ajustes-stock")

    cfg = get_configuracion_stock()
    productos_en_stock = get_configuracion_stock_productos_en_stock()
    return render_template("ajustes_stock.html", cfg=cfg, productos_en_stock=productos_en_stock)


@usuarios_bp.route("/ubicaciones", methods=["GET", "POST"])
def ubicaciones_admin():
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()

        if not nombre:
            flash("Ingresa un nombre de ubicacion", "error")
            return redirect("/admin/ubicaciones")

        try:
            existentes = [u.lower() for u in get_ubicaciones()]
            if nombre.lower() in existentes:
                flash("La ubicacion ya existe", "error")
                return redirect("/admin/ubicaciones")

            add_ubicacion(nombre)
            flash("Ubicacion agregada correctamente", "success")
        except Exception as e:
            flash(f"No se pudo agregar la ubicacion: {str(e)}", "error")

        return redirect("/admin/ubicaciones")

    return render_template("ubicaciones.html", ubicaciones=get_ubicaciones())


@usuarios_bp.route("/ubicaciones/eliminar/<path:nombre>", methods=["POST"])
def eliminar_ubicacion(nombre):
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    try:
        delete_ubicacion(nombre)
        flash("Ubicacion eliminada", "success")
    except Exception as e:
        flash(f"No se pudo eliminar la ubicacion: {str(e)}", "error")

    return redirect("/admin/ubicaciones")


@usuarios_bp.route("/accesos")
def accesos_login_admin():
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    usuario_filtro = (request.args.get("usuario") or "").strip()
    fecha_desde = (request.args.get("fecha_desde") or "").strip()
    fecha_hasta = (request.args.get("fecha_hasta") or "").strip()

    for campo, valor in (("fecha_desde", fecha_desde), ("fecha_hasta", fecha_hasta)):
        if valor:
            try:
                datetime.strptime(valor, "%Y-%m-%d")
            except ValueError:
                flash(f"Formato invalido en {campo}. Usa YYYY-MM-DD", "error")
                return redirect("/admin/accesos")

    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        flash("El rango de fechas es invalido", "error")
        return redirect("/admin/accesos")

    try:
        accesos = get_accesos_login(
            200,
            username=usuario_filtro or None,
            fecha_desde=fecha_desde or None,
            fecha_hasta=fecha_hasta or None,
        )
    except Exception as e:
        flash(f"No se pudo cargar el historial de accesos: {str(e)}", "error")
        accesos = []

    return render_template(
        "accesos_login.html",
        accesos=accesos,
        filtros={
            "usuario": usuario_filtro,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        },
    )


# 🔍 AUDITORÍA: Ver registro de acciones administrativas

@usuarios_bp.route('/auditoria')
def auditoria():
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    accion_filtro = request.args.get('accion', '')
    usuario_filtro = request.args.get('usuario', '')
    limit = int(request.args.get('limit', '200'))
    
    try:
        registros = get_auditoria(
            accion=accion_filtro or None,
            username=usuario_filtro or None,
            limit=min(limit, 500)  # Máximo 500
        )
    except Exception as e:
        flash(f"No se pudo cargar auditoría: {str(e)}", "error")
        registros = []
    
    # Acciones únicas para el dropdown de filtro
    try:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT accion FROM system_events WHERE evento = 'admin_action' ORDER BY accion")
        acciones_disponibles = [row[0] for row in cursor.fetchall()]
        conn.close()
    except:
        acciones_disponibles = []
    
    return render_template(
        "auditoria.html",
        registros=registros,
        acciones_disponibles=acciones_disponibles,
        filtros={'accion': accion_filtro, 'usuario': usuario_filtro, 'limit': limit}
    )


# 🚨 ALERTAS: Ver condiciones críticas del sistema

@usuarios_bp.route('/alertas')
def alertas_sistema():
    if "rol" not in session or session["rol"] not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    try:
        condiciones_alerta = get_alertas_condiciones()
        hay_alertas = len(condiciones_alerta) > 0
    except Exception as e:
        flash(f"No se pudo cargar alertas: {str(e)}", "error")
        condiciones_alerta = {}
        hay_alertas = False
    
    # Obtener correos de admins para mostrar (sin enviar emails aún)
    try:
        correos_admin = get_usuarios_admin_email()
    except:
        correos_admin = []
    
    return render_template(
        "alertas_sistema.html",
        condiciones_alerta=condiciones_alerta,
        hay_alertas=hay_alertas,
        correos_admin=correos_admin
    )


# 🧹 LIMPIEZA: Ejecutar limpieza manual de datos expirados

@usuarios_bp.route('/limpiar-expirados', methods=['POST'])
def limpiar_expirados_manual():
    if "rol" not in session or session["rol"] != "superadmin":
        return render_template("acceso_denegado.html"), 403
    
    try:
        resultado = limpiar_datos_expirados()
        registrar_accion_admin(
            accion='limpiar_expirados_manual',
            username=session.get('username', 'desconocido'),
            estado='ok',
            detalle=f"Códigos: {resultado['deleted_codes']}, Usuarios desbloqueados: {resultado['unblocked_users']}, Emails: {resultado['deleted_emails']}, Sesiones: {resultado['deleted_sessions']}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        flash(f"Limpieza completada. Eliminados {resultado['deleted_codes']} códigos, {resultado['deleted_emails']} emails, {resultado['deleted_sessions']} sesiones.", "success")
    except Exception as e:
        registrar_accion_admin(
            accion='limpiar_expirados_manual',
            username=session.get('username', 'desconocido'),
            estado='error',
            detalle=str(e)[:220],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        flash(f"Error en limpieza: {str(e)}", "error")
    
    return redirect("/admin/alertas")