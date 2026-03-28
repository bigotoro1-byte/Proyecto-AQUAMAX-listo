from flask import Blueprint, render_template, session, redirect
from database.db import conectar
from routes.utils import login_required

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT SUM(cantidad) FROM inventario")
    total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM productos")
    total_productos = cursor.fetchone()[0] or 0

    cursor.execute("""
    SELECT producto, SUM(cantidad)
    FROM inventario GROUP BY producto
    """)
    data = cursor.fetchall()

    productos = [d[0] for d in data]
    cantidades = [d[1] for d in data]

    cursor.execute("""
    SELECT producto, SUM(cantidad)
    FROM inventario
    GROUP BY producto
    HAVING SUM(cantidad) < 10
    """)
    alertas = cursor.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total=total,
        total_productos=total_productos,
        productos=productos,
        cantidades=cantidades,
        alertas=alertas
    )

from flask import request

@dashboard_bp.route("/reporte")
@login_required
def reporte():

    conn = conectar()
    cursor = conn.cursor()

    # 🔽 obtener filtros
    producto = request.args.get("producto")
    ubicacion = request.args.get("ubicacion")

    # 🔽 opciones para dropdown
    cursor.execute("SELECT nombre FROM productos")
    lista_productos = [p[0] for p in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT piscina FROM inventario")
    lista_ubicaciones = [u[0] for u in cursor.fetchall() if u[0]]

    # 🔽 query principal
    query = """
        SELECT p.nombre, IFNULL(i.piscina, 'Sin movimiento'), IFNULL(SUM(i.cantidad), 0)
        FROM productos p
        LEFT JOIN inventario i ON p.nombre = i.producto
        WHERE 1=1
    """

    params = []

    if producto:
        query += " AND p.nombre = ?"
        params.append(producto)

    if ubicacion:
        query += " AND i.piscina = ?"
        params.append(ubicacion)

    query += " GROUP BY p.nombre, i.piscina"

    cursor.execute(query, params)
    datos = cursor.fetchall()

    conn.close()

    return render_template(
        "reporte.html",
        reporte=datos,
        lista_productos=lista_productos,
        lista_ubicaciones=lista_ubicaciones
    )


from flask import session, redirect
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
import os

if not os.path.exists("reportes"):
    os.makedirs("reportes")

@dashboard_bp.route("/reporte/pdf")
def generar_pdf():

    import os
    import uuid
    from datetime import datetime
    from flask import send_file, request, session
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet

    # 📁 carpeta
    if not os.path.exists("reportes"):
        os.makedirs("reportes")

    # 🔥 código único auditoría
    codigo_reporte = str(uuid.uuid4())[:8]

    ruta_pdf = f"reportes/reporte_{codigo_reporte}.pdf"

    # 🔗 conexión
    conn = conectar()
    cursor = conn.cursor()

    # 🔍 filtros
    producto = request.args.get("producto")
    ubicacion = request.args.get("ubicacion")

    query = """
    SELECT producto, piscina, SUM(cantidad)
    FROM inventario
    WHERE 1=1
    """

    params = []

    if producto:
        query += " AND producto = ?"
        params.append(producto)

    if ubicacion:
        query += " AND piscina = ?"
        params.append(ubicacion)

    query += " GROUP BY producto, piscina"

    cursor.execute(query, params)
    datos = cursor.fetchall()

    conn.close()

    # 📄 PDF
    pdf = SimpleDocTemplate(ruta_pdf)
    styles = getSampleStyleSheet()

    elementos = []

    # 🖼️ LOGO
    if os.path.exists("static/logo.png"):
        elementos.append(Image("static/logo.png", width=120, height=60))

    elementos.append(Spacer(1, 10))

    # 🏢 ENCABEZADO
    elementos.append(Paragraph("AQUAMAX", styles["Title"]))
    elementos.append(Paragraph("REPORTE DE INVENTARIO - AQUQMAX", styles["Heading2"]))
    elementos.append(Spacer(1, 10))

    # 📌 INFO AUDITORÍA
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    usuario = session.get("user", "Sistema")

    elementos.append(Paragraph(f"Código de reporte: {codigo_reporte}", styles["Normal"]))
    elementos.append(Paragraph(f"Generado por: {usuario}", styles["Normal"]))
    elementos.append(Paragraph(f"Fecha: {fecha}", styles["Normal"]))

    # 🔍 filtros visibles
    if producto:
        elementos.append(Paragraph(f"Filtro producto: {producto}", styles["Normal"]))
    if ubicacion:
        elementos.append(Paragraph(f"Filtro ubicación: {ubicacion}", styles["Normal"]))

    elementos.append(Spacer(1, 15))

    # 📊 TABLA
    tabla_data = [["Producto", "Ubicación", "Cantidad"]]

    for d in datos:
        tabla_data.append([str(d[0]), str(d[1]), str(d[2])])

    tabla = Table(tabla_data)

    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('FONTNAME',(0,0),(-1,0),"Helvetica-Bold"),
    ]))

    elementos.append(tabla)

    # ✍️ FIRMA
    elementos.append(Spacer(1, 40))
    elementos.append(Paragraph("__________________________", styles["Normal"]))
    elementos.append(Paragraph("Firma responsable", styles["Normal"]))

    # 🏁 GENERAR
    pdf.build(elementos)

    return send_file(ruta_pdf, as_attachment=True)