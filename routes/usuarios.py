from flask import Blueprint, render_template, request, redirect, session
from database.db import conectar
from werkzeug.security import generate_password_hash

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/admin")


# 🔐 LISTAR Y CREAR USUARIOS
@usuarios_bp.route("/usuarios", methods=["GET", "POST"])
def usuarios():

    if "rol" not in session or session["rol"] != "admin":
        return "No tienes permisos"

    conn = conectar()
    cursor = conn.cursor()

    # 👉 CREAR USUARIO
    if request.method == "POST":
        user = request.form.get("usuario")
        password = request.form.get("password")
        rol = request.form.get("rol")

        if not user or not password or not rol:
            return render_template("usuarios.html", error="Completa todos los campos")

        try:
            cursor.execute(
                "INSERT INTO usuarios VALUES (?, ?, ?)",
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
@usuarios_bp.route("/usuarios/eliminar/<user>")
def eliminar_usuario(user):

    if "rol" not in session or session["rol"] != "admin":
        return "No tienes permisos"

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM usuarios WHERE user=?", (user,))
    conn.commit()
    conn.close()

    return redirect("/admin/usuarios")