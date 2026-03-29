import sqlite3
import os

try:
    import psycopg2
    import psycopg2.extensions
except:
    psycopg2 = None


def es_postgres(conn):
    return psycopg2 and isinstance(conn, psycopg2.extensions.connection)


def conectar():
    database_url = os.environ.get("DATABASE_URL")

    try:
        if database_url and psycopg2:
            return psycopg2.connect(database_url)

        return sqlite3.connect("aquamax.db")

    except Exception as e:
        print("Error de conexión:", e)
        return sqlite3.connect("aquamax.db")


def ejecutar(cursor, conn, query, params=()):
    if es_postgres(conn):
        query = query.replace("?", "%s")
    cursor.execute(query, params)


def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    ejecutar(cursor, conn, """
    CREATE TABLE IF NOT EXISTS productos (
        id TEXT PRIMARY KEY,
        nombre TEXT,
        tipo TEXT,
        fecha TEXT,
        usuario TEXT
    )
    """)

    if es_postgres(conn):
        ejecutar(cursor, conn, """
        CREATE TABLE IF NOT EXISTS inventario (
            id SERIAL PRIMARY KEY,
            producto TEXT,
            cantidad REAL,
            piscina TEXT,
            fecha TEXT,
            usuario TEXT
        )
        """)
    else:
        ejecutar(cursor, conn, """
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto TEXT,
            cantidad REAL,
            piscina TEXT,
            fecha TEXT,
            usuario TEXT
        )
        """)

    ejecutar(cursor, conn, """
    CREATE TABLE IF NOT EXISTS usuarios (
        user TEXT PRIMARY KEY,
        password TEXT,
        rol TEXT
    )
    """)

    conn.commit()
    conn.close()


def actualizar_tabla():
    conn = conectar()
    cursor = conn.cursor()

    try:
        ejecutar(cursor, conn, "ALTER TABLE productos ADD COLUMN fecha TEXT")
    except:
        pass

    try:
        ejecutar(cursor, conn, "ALTER TABLE productos ADD COLUMN usuario TEXT")
    except:
        pass

    conn.commit()
    conn.close()