from flask import Blueprint, render_template, request, session
from database.db import conectar
from datetime import datetime

productos_bp = Blueprint("productos", __name__)

@productos_bp.route("/productos", methods=["GET", "POST"])
def productos():

    if session.get("rol") != "admin":
        return "Acceso denegado"

    conn = conectar()
    cursor = conn.cursor()

    mensaje = None

    if request.method == "POST":

        codigo = request.form.get("codigo")
        producto = request.form.get("producto")
        tipo = request.form.get("tipo")

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        usuario = session.get("user")

        if not codigo or not producto:
            mensaje = "❌ Faltan datos"

        else:
            cursor.execute("SELECT * FROM productos WHERE id=?", (codigo,))
            existe = cursor.fetchone()

            if existe:
                mensaje = "❌ El código ya existe"
            else:
                cursor.execute(
                    "INSERT INTO productos (id, nombre, tipo, fecha, usuario) VALUES (?, ?, ?, ?, ?)",
                    (codigo, producto, tipo, fecha, usuario)
                )
                conn.commit()
                mensaje = "✅ Producto agregado"

    cursor.execute("SELECT * FROM productos")
    datos = cursor.fetchall()

    conn.close()

    return render_template("productos.html", datos=datos, mensaje=mensaje)