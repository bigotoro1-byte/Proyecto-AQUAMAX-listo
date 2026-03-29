from flask import Flask
from database.db import crear_tablas, actualizar_tabla, conectar
from werkzeug.security import generate_password_hash

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.inventario import inventario_bp
from routes.productos import productos_bp
from routes.usuarios import usuarios_bp
print("Usuarios blueprint cargado")


app = Flask(__name__)
app.secret_key = "aquamax_secret"

# 🔌 DB
crear_tablas()

# 🔥 ORDEN CORRECTO
crear_tablas()
actualizar_tabla()

# 🔐 CREAR ADMIN AUTOMÁTICO
def crear_admin():
    conn = conectar()
    cursor = conn.cursor()
    password = generate_password_hash("1234")

    cursor.execute(
        "INSERT INTO usuarios (username, password, rol)",
        ("admin", password, "admin")
    )

    conn.commit()
    conn.close()

crear_admin()

# 🔗 RUTAS
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(inventario_bp)
app.register_blueprint(productos_bp)
app.register_blueprint(usuarios_bp)
print(app.url_map)

# 🚀 RUN
if __name__ == "__main__":
    app.run(debug=True, port=5001)