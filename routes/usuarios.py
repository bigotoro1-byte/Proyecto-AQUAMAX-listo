from flask import Blueprint, render_template, request, redirect, session, flash
from database.db import conectar, get_configuracion_stock, set_configuracion_stock, get_configuracion_stock_productos_en_stock, set_configuracion_stock_producto, get_ubicaciones, add_ubicacion, delete_ubicacion
from werkzeug.security import generate_password_hash
from datetime import datetime
import os
import shutil
import re

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/admin")


def password_es_fuerte(password):
    if not password or len(password) < 8:
        return False
    return bool(re.search(r"[A-Za-z]", password) and re.search(r"\d", password))


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

        if not user or not password or not rol:
            return render_template("usuarios.html", error="Completa todos los campos")

        if not password_es_fuerte(password):
            return render_template("usuarios.html", error="La contraseña debe tener al menos 8 caracteres, letras y numeros")

        if rol == "superadmin" and session.get("rol") != "superadmin":
            return render_template("usuarios.html", error="Solo superadmin puede crear otro superadmin")

        try:
            cursor.execute(
                "INSERT INTO usuarios (username, password, rol) VALUES (%s, %s, %s)",
                (user, generate_password_hash(password), rol)
            )
            conn.commit()
        except:
            return render_template("usuarios.html", error="Usuario ya existe")

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
        return redirect("/admin/usuarios")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM usuarios WHERE username=%s", (user,))
    conn.commit()
    conn.close()

    return redirect("/admin/usuarios")


def _crear_respaldo_db():
    # Con PostgreSQL el backup de archivo local no aplica.
    # El respaldo se gestiona desde el panel de Render (PostgreSQL Backups).
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"backup_postgres_{stamp} (gestionado por Render)"


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
                flash(f"Inventario limpiado. Respaldo: {backup_path}", "success")

            elif action == "reiniciar_datos":
                if confirm != "REINICIAR":
                    flash("Confirmacion invalida. Escribe REINICIAR.", "error")
                    return redirect("/admin/sistema")

                cursor.execute("DELETE FROM inventario")
                cursor.execute("DELETE FROM productos")
                cursor.execute("DELETE FROM usuarios WHERE rol NOT IN ('admin', 'superadmin')")
                conn.commit()
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