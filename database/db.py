import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

def conectar():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL no está configurado.')
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    return conn

def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    # Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        rol TEXT NOT NULL
    )
    """)

    # Productos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        tipo TEXT,
        fecha TEXT,
        usuario TEXT
    )
    """)

    # Inventario
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventario (
        id SERIAL PRIMARY KEY,
        producto TEXT NOT NULL,
        cantidad REAL NOT NULL,
        piscina TEXT NOT NULL,
        fecha TEXT,
        usuario TEXT
    )
    """)

    # Movimientos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        id SERIAL PRIMARY KEY,
        producto TEXT NOT NULL,
        tipo TEXT NOT NULL,
        cantidad REAL NOT NULL,
        ubicacion TEXT,
        fecha TEXT,
        usuario TEXT
    )
    """)

    # Configuracion general
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    )
    """)

    # Configuracion por producto
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_producto (
        producto TEXT PRIMARY KEY,
        umbral_critico REAL NOT NULL,
        umbral_medio REAL NOT NULL,
        umbral_alerta_dashboard REAL NOT NULL
    )
    """)

    # Ubicaciones configurables para salida
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ubicaciones (
        nombre TEXT PRIMARY KEY
    )
    """)

    # Indices para rendimiento en consultas frecuentes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_producto_piscina ON inventario(producto, piscina)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_fecha ON inventario(fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_usuario_tipo ON movimientos(usuario, tipo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos(fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cfg_producto_producto ON configuracion_producto(producto)")

    # Valores por defecto para ajustes de stock
    defaults = {
        'min_cantidad_entrada': '0.01',
        'min_cantidad_salida': '0.01',
        'umbral_critico': '5',
        'umbral_medio': '15',
        'umbral_alerta_dashboard': '10'
    }
    for clave, valor in defaults.items():
        cursor.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO NOTHING",
            (clave, valor)
        )

    ubicaciones_default = ["Piscina", "Pasillos", "Oficinas", "Otros"]
    for nombre in ubicaciones_default:
        cursor.execute(
            "INSERT INTO ubicaciones (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING",
            (nombre,)
        )

    conn.commit()
    conn.close()

def actualizar_tabla():
    # Migraciones si es necesario
    pass

# Funciones seguras con prepared statements
def insert_usuario(username, password, rol):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (username, password, rol) VALUES (%s, %s, %s) ON CONFLICT (username) DO UPDATE SET password=EXCLUDED.password, rol=EXCLUDED.rol",
            (username, password, rol)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_usuario(username):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def actualizar_contrasena(username, new_password_hash):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET password = %s WHERE username = %s", (new_password_hash, username))
    conn.commit()
    conn.close()

def insert_producto(id, nombre, tipo, fecha, usuario):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO productos (id, nombre, tipo, fecha, usuario) VALUES (%s, %s, %s, %s, %s)",
            (id, nombre, tipo, fecha, usuario)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_productos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM productos ORDER BY nombre")
    productos = cursor.fetchall()
    conn.close()
    return productos

def insert_inventario(producto, cantidad, piscina, fecha, usuario):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO inventario (producto, cantidad, piscina, fecha, usuario) VALUES (%s, %s, %s, %s, %s)",
            (producto, cantidad, piscina, fecha, usuario)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_inventario(user=None):
    conn = conectar()
    cursor = conn.cursor()
    if user:
        cursor.execute("SELECT * FROM inventario WHERE usuario = %s", (user,))
    else:
        cursor.execute("SELECT * FROM inventario")
    inventario = cursor.fetchall()
    conn.close()
    return inventario

def get_stock_actual():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(p.nombre, i.producto) AS producto_nombre, i.piscina, SUM(i.cantidad), i.usuario
        FROM inventario i
        LEFT JOIN productos p ON p.id = i.producto
        WHERE i.piscina = 'GENERAL'
        GROUP BY COALESCE(p.nombre, i.producto), i.piscina, i.usuario
    """)
    stock = cursor.fetchall()
    conn.close()
    return stock


def get_stock_general_por_producto():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT producto, COALESCE(SUM(cantidad), 0)
        FROM inventario
        WHERE piscina = 'GENERAL'
        GROUP BY producto
        """
    )
    data = {row[0]: float(row[1] or 0) for row in cursor.fetchall()}
    conn.close()
    return data


def get_configuracion_stock():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT clave, valor FROM configuracion")
    rows = cursor.fetchall()
    conn.close()

    config = {
        'min_cantidad_entrada': 0.01,
        'min_cantidad_salida': 0.01,
        'umbral_critico': 5.0,
        'umbral_medio': 15.0,
        'umbral_alerta_dashboard': 10.0,
    }

    for clave, valor in rows:
        if clave in config:
            try:
                config[clave] = float(valor)
            except (TypeError, ValueError):
                pass

    return config


def set_configuracion_stock(config_dict):
    conn = conectar()
    cursor = conn.cursor()
    try:
        for clave, valor in config_dict.items():
            cursor.execute(
                "INSERT INTO configuracion (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO UPDATE SET valor=EXCLUDED.valor",
                (clave, str(valor))
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def set_configuracion_stock_producto(producto_id, umbral_critico, umbral_medio, umbral_alerta_dashboard):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO configuracion_producto (producto, umbral_critico, umbral_medio, umbral_alerta_dashboard)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (producto) DO UPDATE SET
                umbral_critico=EXCLUDED.umbral_critico,
                umbral_medio=EXCLUDED.umbral_medio,
                umbral_alerta_dashboard=EXCLUDED.umbral_alerta_dashboard
            """,
            (producto_id, float(umbral_critico), float(umbral_medio), float(umbral_alerta_dashboard))
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_configuracion_stock_productos_en_stock():
    cfg = get_configuracion_stock()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            p.id,
            p.nombre,
            COALESCE(SUM(i.cantidad), 0) AS stock_general,
            COALESCE(cp.umbral_critico, %s) AS umbral_critico,
            COALESCE(cp.umbral_medio, %s) AS umbral_medio,
            COALESCE(cp.umbral_alerta_dashboard, %s) AS umbral_alerta_dashboard
        FROM productos p
        LEFT JOIN inventario i ON p.id = i.producto AND i.piscina = 'GENERAL'
        LEFT JOIN configuracion_producto cp ON cp.producto = p.id
        GROUP BY p.id, p.nombre, cp.umbral_critico, cp.umbral_medio, cp.umbral_alerta_dashboard
        HAVING COALESCE(SUM(i.cantidad), 0) > 0
        ORDER BY p.nombre
        """,
        (cfg['umbral_critico'], cfg['umbral_medio'], cfg['umbral_alerta_dashboard'])
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_configuracion_stock_producto_map_por_nombre():
    rows = get_configuracion_stock_productos_en_stock()
    return {
        r[1]: {
            'umbral_critico': float(r[3]),
            'umbral_medio': float(r[4]),
            'umbral_alerta_dashboard': float(r[5]),
        }
        for r in rows
    }


def insert_movimiento(producto, tipo, cantidad, ubicacion, fecha, usuario):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO movimientos (producto, tipo, cantidad, ubicacion, fecha, usuario) VALUES (%s, %s, %s, %s, %s, %s)",
            (producto, tipo, cantidad, ubicacion, fecha, usuario)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_movimientos_salida(limit=10, usuario=None):
    conn = conectar()
    cursor = conn.cursor()
    if usuario:
        cursor.execute(
            """
            SELECT COALESCE(p.nombre, m.producto), m.tipo, m.cantidad, m.ubicacion, m.fecha, m.usuario
            FROM movimientos m
            LEFT JOIN productos p ON p.id = m.producto
            WHERE m.tipo = 'SALIDA' AND m.usuario = %s
            ORDER BY m.id DESC
            LIMIT %s
            """,
            (usuario, limit),
        )
    else:
        cursor.execute(
            """
            SELECT COALESCE(p.nombre, m.producto), m.tipo, m.cantidad, m.ubicacion, m.fecha, m.usuario
            FROM movimientos m
            LEFT JOIN productos p ON p.id = m.producto
            WHERE m.tipo = 'SALIDA'
            ORDER BY m.id DESC
            LIMIT %s
            """,
            (limit,),
        )
    data = cursor.fetchall()
    conn.close()
    return data


def get_ubicaciones():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM ubicaciones ORDER BY nombre")
    data = [row[0] for row in cursor.fetchall()]
    conn.close()
    return data


def add_ubicacion(nombre):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ubicaciones (nombre) VALUES (%s)",
            (nombre,)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def delete_ubicacion(nombre):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ubicaciones WHERE nombre = %s", (nombre,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def descontar_stock(producto, cantidad, usuario=None):
    conn = conectar()
    cursor = conn.cursor()
    try:
        # Obtener entradas en GENERAL ordenadas por fecha (cualquier usuario)
        cursor.execute(
            "SELECT id, cantidad FROM inventario WHERE producto = %s AND piscina = 'GENERAL' ORDER BY fecha",
            (producto,)
        )
        entradas = cursor.fetchall()

        cantidad_restante = cantidad
        for entrada_id, entrada_cantidad in entradas:
            if cantidad_restante <= 0:
                break
            if entrada_cantidad > cantidad_restante:
                nueva_cantidad = entrada_cantidad - cantidad_restante
                cursor.execute(
                    "UPDATE inventario SET cantidad = %s WHERE id = %s",
                    (nueva_cantidad, entrada_id)
                )
                cantidad_restante = 0
            else:
                cursor.execute("DELETE FROM inventario WHERE id = %s", (entrada_id,))
                cantidad_restante -= entrada_cantidad

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
