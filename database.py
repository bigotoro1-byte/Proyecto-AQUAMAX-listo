import sqlite3

def conectar():
    return sqlite3.connect("aquamax.db")

def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id TEXT PRIMARY KEY,
        nombre TEXT,
        tipo TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventario (
        id TEXT,
        producto TEXT,
        tipo TEXT,
        cantidad REAL,
        piscina TEXT,
        fecha TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        usuario TEXT,
        accion TEXT,
        producto TEXT,
        cantidad REAL,
        fecha TEXT
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