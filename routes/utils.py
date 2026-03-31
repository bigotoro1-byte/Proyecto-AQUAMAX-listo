from functools import wraps
from flask import session, redirect, render_template

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        if session.get("debe_cambiar_password"):
            return redirect("/cambiar_contrasena")
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("rol") not in ("admin", "superadmin"):
            return render_template("acceso_denegado.html"), 403
        return f(*args, **kwargs)
    return decorated