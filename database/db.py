import sqlite3
import psycopg2
import os

def conectar():
    database_url = os.environ.get("DATABASE_URL")
<<<<<<< HEAD

    try:
        # 🔥 Si hay URL → PostgreSQL (Render)
        if database_url:
            return psycopg2.connect(database_url)

        # 💻 Local → SQLite
        return sqlite3.connect("aquamax.db")

    except Exception as e:
        print("Error de conexión:", e)
        return sqlite3.connect("aquamax.db")

    # 🔥 SI ESTÁ EN RENDER → USA POSTGRESQL
    if database_url:
        return psycopg2.connect(database_url)

    # 💻 SI ESTÁS EN LOCAL → USA SQLITE
    return sqlite3.connect("aquamax.db")
=======
>>>>>>> b10f179 (conexion dual sqlite + postgres)

    try:
        # 🔥 Si hay URL → PostgreSQL (Render)
        if database_url:
            return psycopg2.connect(database_url)

        # 💻 Local → SQLite
        return sqlite3.connect("aquamax.db")

    except Exception as e:
        print("Error de conexión:", e)
        return sqlite3.connect("aquamax.db")

# 🔥 CREAR TABLAS SI NO EXISTEN
def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id TEXT PRIMARY KEY,
        nombre TEXT,
        tipo TEXT,
        fecha TEXT,
        usuario TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto TEXT,
        cantidad REAL,
        piscina TEXT,
        fecha TEXT,
        usuario TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        user TEXT PRIMARY KEY,
        password TEXT,
        rol TEXT
    )
    """)

    conn.commit()
    conn.close()


# 🔥 MIGRACIÓN SEGURA (NO ROMPE)
def actualizar_tabla():
    conn = conectar()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE productos ADD COLUMN fecha TEXT")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE productos ADD COLUMN usuario TEXT")
    except:
        pass

    conn.commit()
    conn.close()
