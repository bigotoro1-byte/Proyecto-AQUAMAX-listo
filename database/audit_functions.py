# Funciones de auditoría, limpieza y alertas para agregar a db.py

"""
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
    - Intentos de login fallidos en últimas 2 horas > umbral
    - Usuarios bloqueados
    - DB crítica (>80% de límite estimado)
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
            horas_diff = (datetime.now(ultimo_backup[0].tzinfo) - ultimo_backup[0]).total_seconds() / 3600
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
"""
