from flask import Blueprint, render_template, request, session, redirect, flash
from database.db import conectar, registrar_accion_admin
from datetime import datetime
import uuid

productos_bp = Blueprint("productos", __name__)


def generar_codigo_producto(cursor):
    while True:
        codigo = f"PRD-{uuid.uuid4().hex[:8].upper()}"
        cursor.execute("SELECT 1 FROM productos WHERE id = %s", (codigo,))
        if not cursor.fetchone():
            return codigo


@productos_bp.route("/productos/editar-nombre/<producto_id>", methods=["POST"])
def editar_nombre_producto(producto_id):

    if session.get("rol") != "superadmin":
        return render_template("acceso_denegado.html"), 403

    nuevo_nombre = (request.form.get("nuevo_nombre") or "").strip()
    if not nuevo_nombre:
        flash("Debes ingresar un nombre valido para el producto.", "error")
        return redirect("/productos")

    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nombre FROM productos WHERE id = %s", (producto_id,))
        row = cursor.fetchone()
        if not row:
            flash("Producto no encontrado.", "error")
            return redirect("/productos")

        nombre_actual = (row[0] or "").strip()
        if nombre_actual.lower() == nuevo_nombre.lower():
            flash("El nuevo nombre es igual al actual.", "error")
            return redirect("/productos")

        cursor.execute(
            "SELECT 1 FROM productos WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(%s)) AND id <> %s",
            (nuevo_nombre, producto_id)
        )
        if cursor.fetchone():
            flash("Ya existe otro producto con ese nombre.", "error")
            registrar_accion_admin(
                accion='editar_nombre_producto',
                username=session.get('user', 'desconocido'),
                estado='error',
                detalle=f'Intento duplicado. Producto: {producto_id}, Nombre: {nuevo_nombre}',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')
            )
            return redirect("/productos")

        cursor.execute("UPDATE productos SET nombre = %s WHERE id = %s", (nuevo_nombre, producto_id))
        conn.commit()
        registrar_accion_admin(
            accion='editar_nombre_producto',
            username=session.get('user', 'desconocido'),
            estado='ok',
            detalle=f'Producto: {producto_id}, Antes: {nombre_actual}, Ahora: {nuevo_nombre}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        flash("Nombre del producto actualizado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        registrar_accion_admin(
            accion='editar_nombre_producto',
            username=session.get('user', 'desconocido'),
            estado='error',
            detalle=str(e)[:220],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        flash(f"No se pudo actualizar el nombre del producto: {str(e)}", "error")
    finally:
        conn.close()

    return redirect("/productos")

@productos_bp.route("/productos", methods=["GET", "POST"])
def productos():

    if session.get("rol") not in ("admin", "superadmin"):
        return render_template("acceso_denegado.html"), 403

    conn = conectar()
    cursor = conn.cursor()

    mensaje = None
    codigo_generado = None

    if request.method == "POST":

        producto = (request.form.get("producto") or "").strip()
        tipo = (request.form.get("tipo") or "").strip()

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        usuario = session.get("user")

        if not producto:
            mensaje = "❌ Faltan datos"

        else:
            cursor.execute(
                "SELECT 1 FROM productos WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(%s))",
                (producto,)
            )
            existe_nombre = cursor.fetchone()

            if existe_nombre:
                mensaje = "❌ Ya existe un producto con ese nombre"
                registrar_accion_admin(
                    accion='crear_producto',
                    username=session.get('user', 'desconocido'),
                    estado='error',
                    detalle=f'Producto duplicado: {producto}',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
            else:
                codigo_generado = generar_codigo_producto(cursor)
                cursor.execute(
                    "INSERT INTO productos (id, nombre, tipo, fecha, usuario) VALUES (%s, %s, %s, %s, %s)",
                    (codigo_generado, producto, tipo, fecha, usuario)
                )
                conn.commit()
                registrar_accion_admin(
                    accion='crear_producto',
                    username=session.get('user', 'desconocido'),
                    estado='ok',
                    detalle=f'Producto: {producto}, Codigo: {codigo_generado}, Tipo: {tipo or "-"}',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                flash(f"Producto agregado con código {codigo_generado}", "success")
                conn.close()
                return redirect("/productos")

    cursor.execute("SELECT * FROM productos")
    datos = cursor.fetchall()

    conn.close()

    return render_template("productos.html", datos=datos, mensaje=mensaje, codigo_generado=codigo_generado)