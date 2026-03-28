from flask import Blueprint, render_template, request, session, redirect
from database.db import conectar
from datetime import datetime
from routes.utils import login_required

inventario_bp = Blueprint("inventario", __name__)

@inventario_bp.route("/inventario", methods=["GET","POST"])
@login_required
def inventario():

    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":

        producto = request.form.get("producto")
        cantidad = float(request.form.get("cantidad") or 0)

        # 🔥 SIEMPRE GENERAL
        piscina = "GENERAL"

        cursor.execute(
            "INSERT INTO inventario (producto, cantidad, piscina) VALUES (?, ?, ?)",
            (producto, cantidad, piscina)
        )
        conn.commit()

    cursor.execute("SELECT nombre FROM productos")
    productos = cursor.fetchall()

    cursor.execute("""
        SELECT producto, piscina, SUM(cantidad), usuario
        FROM inventario
        GROUP BY producto, piscina, usuario
        """)
    stock_actual = cursor.fetchall()

    if session.get("rol") == "admin":
        cursor.execute("SELECT * FROM inventario")
    else:
        cursor.execute("SELECT * FROM inventario WHERE usuario=?", (session["user"],))

    datos = cursor.fetchall()
    conn.close()

    return render_template(
        "inventario.html",
        datos=datos,
        stock_actual=stock_actual,
        productos=productos
    )

@inventario_bp.route("/salida", methods=["POST"])
def salida():

    producto = request.form.get("producto")
    cantidad = float(request.form.get("cantidad") or 0)
    ubicacion = request.form.get("ubicacion")
    usuario = session.get("user")

    conn = conectar()
    cursor = conn.cursor()

    # 🔥 descontar del GENERAL
    cursor.execute("""
    UPDATE inventario
    SET cantidad = cantidad - ?
    WHERE producto=? AND piscina='GENERAL'
    """, (cantidad, producto))

    # 🔥 registrar movimiento
    cursor.execute("""
    INSERT INTO inventario (producto, cantidad, piscina, usuario)
    VALUES (?, ?, ?, ?)
    """, (producto, cantidad, ubicacion, usuario))

    conn.commit()
    conn.close()

    return redirect("/inventario")