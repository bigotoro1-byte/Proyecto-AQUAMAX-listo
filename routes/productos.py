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