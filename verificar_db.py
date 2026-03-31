from database.db import conectar

conn = conectar()
cursor = conn.cursor()

print("=== USUARIOS ===")
cursor.execute("SELECT username, rol FROM usuarios")
for user in cursor.fetchall():
    print(user)

print("\n=== PRODUCTOS ===")
cursor.execute("SELECT COUNT(*) FROM productos")
print("Total:", cursor.fetchone()[0])

print("\n=== INVENTARIO ===")
cursor.execute("SELECT COUNT(*) FROM inventario")
print("Total movimientos:", cursor.fetchone()[0])

print("\n=== UBICACIONES ===")
cursor.execute("SELECT * FROM ubicaciones")
for ub in cursor.fetchall():
    print(ub[0])

conn.close()
