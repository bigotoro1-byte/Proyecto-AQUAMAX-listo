from flask import Blueprint, render_template, request, redirect, session
from database.db import conectar
from werkzeug.security import check_password_hash

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        user = request.form.get("user")
        password = request.form.get("password")

        if not user or not password:
            return render_template("login.html", error="Completa todos los campos")

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE user=?", (user,))
        usuario = cursor.fetchone()

        conn.close()

        if usuario and check_password_hash(usuario[1], password):
            session["user"] = user
            session["rol"] = usuario[2]
            return redirect("/dashboard")

        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")