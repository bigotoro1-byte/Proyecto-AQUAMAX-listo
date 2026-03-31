import os
import math
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv()

_pool = None

def _get_pool():
    global _pool
    if _pool is None or _pool.closed:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise RuntimeError('DATABASE_URL no está configurado.')
        _pool = ThreadedConnectionPool(1, 5, database_url)
    return _pool


class _PooledConn:
    """Envuelve una conexion psycopg2 para devolverla al pool en conn.close()."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        try:
            self._pool.putconn(self._conn)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def conectar():
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    return _PooledConn(conn, pool)


def _cantidad_positiva(cantidad):
    try:
        valor = float(cantidad)
    except (TypeError, ValueError):
        raise ValueError("Cantidad invalida")
    if not math.isfinite(valor) or valor <= 0:
        raise ValueError("La cantidad debe ser un numero positivo")
    return valor

def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    # Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        rol TEXT NOT NULL,
        email TEXT
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

    # Auditoria de accesos al sistema
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accesos_login (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        rol TEXT,
        ip TEXT,
        user_agent TEXT,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        fecha_salida TIMESTAMP,
        duracion_segundos INTEGER
    )
    """)

    # Estado persistente de intentos de login
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auth_login_state (
        username TEXT PRIMARY KEY,
        failed_count INTEGER NOT NULL DEFAULT 0,
        blocked_until TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    # Estado persistente de recuperacion de contraseña
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS password_recovery_state (
        username TEXT PRIMARY KEY,
        email TEXT,
        codigo TEXT,
        codigo_hash TEXT,
        intentos INTEGER NOT NULL DEFAULT 0,
        expires_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    # Eventos operativos para panel de salud
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_events (
            id SERIAL PRIMARY KEY,
            evento TEXT NOT NULL,
            estado TEXT NOT NULL,
            detalle TEXT,
            username TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    # Log de envios de correo
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_envios_log (
            id SERIAL PRIMARY KEY,
            destino TEXT,
            proveedor TEXT,
            estado TEXT NOT NULL,
            detalle TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    # Indices para rendimiento en consultas frecuentes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_producto_piscina ON inventario(producto, piscina)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_fecha ON inventario(fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_usuario_tipo ON movimientos(usuario, tipo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos(fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cfg_producto_producto ON configuracion_producto(producto)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesos_login_fecha ON accesos_login(fecha DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesos_login_username ON accesos_login(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_login_state_blocked_until ON auth_login_state(blocked_until)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_password_recovery_state_expires_at ON password_recovery_state(expires_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_events_evento_created ON system_events(evento, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_envios_log_created_at ON email_envios_log(created_at DESC)")

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

    conn.commit()
    conn.close()

def actualizar_tabla():
    conn = conectar()
    cursor = conn.cursor()
    try:
        # Migracion: agregar email de recuperacion por usuario
        cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email TEXT")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accesos_login (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                rol TEXT,
                ip TEXT,
                user_agent TEXT,
                fecha TIMESTAMP NOT NULL DEFAULT NOW(),
                fecha_salida TIMESTAMP,
                duracion_segundos INTEGER
            )
            """
        )
        cursor.execute("ALTER TABLE accesos_login ADD COLUMN IF NOT EXISTS fecha_salida TIMESTAMP")
        cursor.execute("ALTER TABLE accesos_login ADD COLUMN IF NOT EXISTS duracion_segundos INTEGER")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesos_login_fecha ON accesos_login(fecha DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesos_login_username ON accesos_login(username)")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_login_state (
                username TEXT PRIMARY KEY,
                failed_count INTEGER NOT NULL DEFAULT 0,
                blocked_until TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS password_recovery_state (
                username TEXT PRIMARY KEY,
                email TEXT,
                codigo TEXT,
                codigo_hash TEXT,
                intentos INTEGER NOT NULL DEFAULT 0,
                expires_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute("ALTER TABLE password_recovery_state ADD COLUMN IF NOT EXISTS codigo_hash TEXT")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_events (
                id SERIAL PRIMARY KEY,
                evento TEXT NOT NULL,
                estado TEXT NOT NULL,
                detalle TEXT,
                username TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS email_envios_log (
                id SERIAL PRIMARY KEY,
                destino TEXT,
                proveedor TEXT,
                estado TEXT NOT NULL,
                detalle TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_login_state_blocked_until ON auth_login_state(blocked_until)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_password_recovery_state_expires_at ON password_recovery_state(expires_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_events_evento_created ON system_events(evento, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_envios_log_created_at ON email_envios_log(created_at DESC)")
        
        # 🔐 Migracion: Auditoría detallada en system_events
        cursor.execute("ALTER TABLE system_events ADD COLUMN IF NOT EXISTS ip_address TEXT")
        cursor.execute("ALTER TABLE system_events ADD COLUMN IF NOT EXISTS user_agent TEXT")
        cursor.execute("ALTER TABLE system_events ADD COLUMN IF NOT EXISTS accion TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_events_accion_created ON system_events(accion, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_events_username_created ON system_events(username, created_at DESC)")
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# Funciones seguras con prepared statements
def insert_usuario(username, password, rol, email=None):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO usuarios (username, password, rol, email)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                password = EXCLUDED.password,
                rol = EXCLUDED.rol,
                email = COALESCE(EXCLUDED.email, usuarios.email)
            """,
            (username, password, rol, email)
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
    cantidad = _cantidad_positiva(cantidad)
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
    cantidad = _cantidad_positiva(cantidad)
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


def get_auth_login_state(username):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT failed_count, blocked_until FROM auth_login_state WHERE LOWER(username) = LOWER(%s)",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def reset_auth_login_state(username):
    if not username:
        return
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM auth_login_state WHERE LOWER(username) = LOWER(%s)", (username,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def register_failed_login(username, max_attempts, lockout_seconds):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT failed_count, blocked_until FROM auth_login_state WHERE LOWER(username) = LOWER(%s)",
            (username,),
        )
        row = cursor.fetchone()
        failed_count = int(row[0]) if row else 0
        failed_count += 1

        blocked_until = None
        stored_count = failed_count
        if failed_count >= int(max_attempts):
            cursor.execute(
                """
                INSERT INTO auth_login_state (username, failed_count, blocked_until, updated_at)
                VALUES (%s, 0, NOW() + (%s * INTERVAL '1 second'), NOW())
                ON CONFLICT (username) DO UPDATE SET
                    failed_count = 0,
                    blocked_until = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                RETURNING blocked_until
                """,
                (username, int(lockout_seconds), int(lockout_seconds)),
            )
            blocked_until = cursor.fetchone()[0]
            stored_count = 0
        else:
            cursor.execute(
                """
                INSERT INTO auth_login_state (username, failed_count, blocked_until, updated_at)
                VALUES (%s, %s, NULL, NOW())
                ON CONFLICT (username) DO UPDATE SET
                    failed_count = EXCLUDED.failed_count,
                    blocked_until = NULL,
                    updated_at = NOW()
                """,
                (username, failed_count),
            )

        conn.commit()
        return stored_count, blocked_until
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def save_password_recovery_state(username, email, codigo_hash, expires_minutes=15):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO password_recovery_state (username, email, codigo, codigo_hash, intentos, expires_at, created_at, updated_at)
            VALUES (%s, %s, NULL, %s, 0, NOW() + (%s * INTERVAL '1 minute'), NOW(), NOW())
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                codigo = NULL,
                codigo_hash = EXCLUDED.codigo_hash,
                intentos = 0,
                expires_at = NOW() + (%s * INTERVAL '1 minute'),
                updated_at = NOW()
            """,
            (username, email, codigo_hash, int(expires_minutes), int(expires_minutes)),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_password_recovery_state(username):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT email, codigo_hash, intentos, expires_at, codigo FROM password_recovery_state WHERE LOWER(username) = LOWER(%s)",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def increment_password_recovery_attempts(username):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE password_recovery_state
            SET intentos = intentos + 1, updated_at = NOW()
            WHERE LOWER(username) = LOWER(%s)
            RETURNING intentos
            """,
            (username,),
        )
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def clear_password_recovery_state(username):
    if not username:
        return
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM password_recovery_state WHERE LOWER(username) = LOWER(%s)", (username,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def registrar_evento_sistema(evento, estado, detalle=None, username=None):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO system_events (evento, estado, detalle, username) VALUES (%s, %s, %s, %s)",
            (evento, estado, (detalle or None), username),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def registrar_email_envio(destino, proveedor, estado, detalle=None):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO email_envios_log (destino, proveedor, estado, detalle) VALUES (%s, %s, %s, %s)",
            (destino, proveedor, estado, (detalle or None)),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_panel_salud(limit_emails=10):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT pg_database_size(current_database())")
        db_size_bytes = int(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COUNT(*) FROM accesos_login WHERE fecha_salida IS NULL")
        sesiones_activas = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM auth_login_state
            WHERE updated_at >= NOW() - INTERVAL '24 hours'
              AND failed_count > 0
            """
        )
        fallos_24h = int(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COUNT(*) FROM auth_login_state WHERE blocked_until IS NOT NULL AND blocked_until > NOW()")
        bloqueos_activos = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT created_at, username, detalle
            FROM system_events
            WHERE evento = 'export_db_xlsx' AND estado = 'ok'
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        ultimo_backup = cursor.fetchone()

        cursor.execute(
            """
            SELECT created_at, proveedor, estado, detalle
            FROM email_envios_log
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        ultimo_email = cursor.fetchone()

        cursor.execute(
            """
            SELECT created_at, destino, proveedor, estado, detalle
            FROM email_envios_log
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (int(limit_emails),),
        )
        emails_recientes = cursor.fetchall()

        return {
            'db_size_bytes': db_size_bytes,
            'sesiones_activas': sesiones_activas,
            'fallos_24h': fallos_24h,
            'bloqueos_activos': bloqueos_activos,
            'ultimo_backup': ultimo_backup,
            'ultimo_email': ultimo_email,
            'emails_recientes': emails_recientes,
        }
    finally:
        conn.close()


def registrar_acceso_login(username, rol=None, ip=None, user_agent=None):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO accesos_login (username, rol, ip, user_agent) VALUES (%s, %s, %s, %s) RETURNING id",
            (username, rol, ip, user_agent),
        )
        acceso_id = cursor.fetchone()[0]
        conn.commit()
        return acceso_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def cerrar_acceso_login(acceso_id):
    if not acceso_id:
        return
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE accesos_login
            SET
                fecha_salida = NOW(),
                duracion_segundos = GREATEST(0, EXTRACT(EPOCH FROM (NOW() - fecha))::int)
            WHERE id = %s AND fecha_salida IS NULL
            """,
            (acceso_id,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def cerrar_accesos_activos_usuario(username):
    if not username:
        return
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE accesos_login
            SET
                fecha_salida = NOW(),
                duracion_segundos = GREATEST(0, EXTRACT(EPOCH FROM (NOW() - fecha))::int)
            WHERE LOWER(username) = LOWER(%s) AND fecha_salida IS NULL
            """,
            (username,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_accesos_login(limit=100, username=None, fecha_desde=None, fecha_hasta=None):
    conn = conectar()
    cursor = conn.cursor()
    query = """
        SELECT
            username,
            rol,
            ip,
            user_agent,
            fecha,
            fecha_salida,
            COALESCE(duracion_segundos, GREATEST(0, EXTRACT(EPOCH FROM (NOW() - fecha))::int)) AS duracion_segundos,
            CASE WHEN fecha_salida IS NULL THEN 'Activa' ELSE 'Cerrada' END AS estado
        FROM accesos_login
        WHERE 1=1
    """
    params = []

    if username:
        query += " AND LOWER(username) LIKE LOWER(%s)"
        params.append(f"%{username.strip()}%")

    if fecha_desde:
        query += " AND fecha >= %s::date"
        params.append(fecha_desde)

    if fecha_hasta:
        query += " AND fecha < (%s::date + INTERVAL '1 day')"
        params.append(fecha_hasta)

    query += " ORDER BY fecha DESC LIMIT %s"
    params.append(limit)

    cursor.execute(query, tuple(params))
    data = cursor.fetchall()
    conn.close()
    return data

def descontar_stock(producto, cantidad, usuario=None):
    cantidad = _cantidad_positiva(cantidad)
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


# 🔐 AUDITORÍA Y LIMPIEZA AUTOMÁTICA

def registrar_accion_admin(accion, username, estado='ok', detalle='', ip_address=None, user_agent=None):
    '''Registra acciones administrativas críticas para auditoría.
    
    accion: tipo de acción (crear_usuario, eliminar_usuario, exportar_db, cambiar_permiso, etc)
    username: usuario que realizó la acción
    estado: 'ok' o 'error'
    detalle: descripción adicional
    ip_address: IP del cliente (para rastreo)
    user_agent: navegador/dispositivo (para rastreo)
    '''
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO system_events (evento, accion, estado, detalle, username, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            ('admin_action', accion, estado, detalle, username, ip_address, user_agent)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_auditoria(accion=None, username=None, limit=100):
    '''Obtiene registros de auditoría (acciones admin).
    
    Si accion es None, obtiene todas las acciones.
    Si username es None, obtiene todas las acciones de todos los usuarios.
    '''
    conn = conectar()
    cursor = conn.cursor()
    try:
        query = "SELECT id, accion, estado, detalle, username, ip_address, created_at FROM system_events WHERE evento = 'admin_action'"
        params = []
        
        if accion:
            query += " AND accion = %s"
            params.append(accion)
        if username:
            query += " AND username = %s"
            params.append(username)
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        conn.close()


def limpiar_datos_expirados():
    '''Limpia datos temporales expirados:
    - Códigos de recuperación expirados
    - Registros de auth fallidos con bloqueo vencido
    - Logs de email antiguos (>90 días)
    - Sesiones cerradas hace >30 días
    '''
    conn = conectar()
    cursor = conn.cursor()
    try:
        # 1. Limpiar códigos de recuperación expirados
        cursor.execute(
            """
            DELETE FROM password_recovery_state
            WHERE expires_at IS NOT NULL AND expires_at < NOW()
            """
        )
        deleted_codes = cursor.rowcount
        
        # 2. Limpiar bloqueos expirados (solo registros, no el contador)
        cursor.execute(
            """
            UPDATE auth_login_state
            SET blocked_until = NULL
            WHERE blocked_until IS NOT NULL AND blocked_until < NOW()
            """
        )
        unblocked_users = cursor.rowcount
        
        # 3. Limpiar logs de email antiguos (>90 días)
        cursor.execute(
            """
            DELETE FROM email_envios_log
            WHERE created_at < NOW() - INTERVAL '90 days'
            """
        )
        deleted_emails = cursor.rowcount
        
        # 4. Limpiar accesos de sesión cerrados hace >30 días
        cursor.execute(
            """
            DELETE FROM accesos_login
            WHERE fecha_salida < NOW() - INTERVAL '30 days'
            """
        )
        deleted_sessions = cursor.rowcount
        
        # Registrar evento de limpieza
        detalle = f"Códigos expirados: {deleted_codes}, Usuarios desbloqueados: {unblocked_users}, Emails antiguos: {deleted_emails}, Sesiones: {deleted_sessions}"
        cursor.execute(
            """
            INSERT INTO system_events (evento, accion, estado, detalle, username)
            VALUES (%s, %s, %s, %s, %s)
            """,
            ('cleanup', 'limpiar_expirados', 'ok', detalle, 'sistema')
        )
        
        conn.commit()
        return {
            'deleted_codes': deleted_codes,
            'unblocked_users': unblocked_users,
            'deleted_emails': deleted_emails,
            'deleted_sessions': deleted_sessions
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_alertas_condiciones():
    '''Obtiene condiciones que deberían generar alertas:
    - Intentos de login fallidos recientes > umbral
    - Usuarios bloqueados
    - DB crítica (>900 MB)
    - Último backup hace >25 horas
    '''
    conn = conectar()
    cursor = conn.cursor()
    try:
        alertas = {}
        
        # 1. Intentos de login fallidos en últimas 2 horas
        cursor.execute(
            """
            SELECT COUNT(*) FROM auth_login_state
            WHERE updated_at >= NOW() - INTERVAL '2 hours'
              AND failed_count >= 3
            """
        )
        intentos_fallidos = int(cursor.fetchone()[0] or 0)
        if intentos_fallidos > 0:
            alertas['login_fallidos'] = {'count': intentos_fallidos, 'descripcion': 'Múltiples intentos fallidos de login'}
        
        # 2. Usuarios bloqueados ahora
        cursor.execute(
            """
            SELECT COUNT(*) FROM auth_login_state
            WHERE blocked_until IS NOT NULL AND blocked_until > NOW()
            """
        )
        bloqueados = int(cursor.fetchone()[0] or 0)
        if bloqueados > 0:
            alertas['usuarios_bloqueados'] = {'count': bloqueados, 'descripcion': 'Usuarios con bloqueo activo'}
        
        # 3. Tamaño DB crítico (>900 MB = 943718400 bytes)
        cursor.execute("SELECT pg_database_size(current_database())")
        db_size = int(cursor.fetchone()[0] or 0)
        if db_size > 943718400:
            size_gb = round(db_size / (1024**3), 2)
            alertas['db_critica'] = {'size': size_gb, 'descripcion': f'BD crítica: {size_gb} GB'}
        
        # 4. Último backup hace >25 horas
        cursor.execute(
            """
            SELECT created_at FROM system_events
            WHERE evento = 'export_db_xlsx' AND estado = 'ok'
            ORDER BY created_at DESC LIMIT 1
            """
        )
        ultimo_backup = cursor.fetchone()
        if ultimo_backup:
            from datetime import datetime, timedelta
            from datetime import timezone
            # Hacer timezone-aware la comparación
            backup_dt = ultimo_backup[0]
            if backup_dt.tzinfo is None:
                backup_dt = backup_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            horas_diff = (now - backup_dt).total_seconds() / 3600
            if horas_diff > 25:
                alertas['backup_viejo'] = {'horas': round(horas_diff), 'descripcion': f'Último backup hace {round(horas_diff)} horas'}
        else:
            alertas['sin_backup'] = {'descripcion': 'Nunca se ha realizado un backup'}
        
        return alertas
    finally:
        conn.close()


def get_usuarios_admin_email():
    '''Obtiene los correos de usuarios con rol admin o superadmin para alertas.'''
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT username, email FROM usuarios
            WHERE rol IN ('admin', 'superadmin') AND email IS NOT NULL
            """
        )
        return cursor.fetchall()
    finally:
        conn.close()
