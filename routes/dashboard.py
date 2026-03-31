from flask import Blueprint, render_template, session, redirect
from database.db import conectar, get_configuracion_stock, get_configuracion_stock_producto_map_por_nombre
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

    cfg = get_configuracion_stock()
    cfg_prod = get_configuracion_stock_producto_map_por_nombre()

    cursor.execute("""
    SELECT p.nombre, COALESCE(SUM(i.cantidad), 0)
    FROM productos p
    LEFT JOIN inventario i ON p.id = i.producto
    GROUP BY p.id, p.nombre
    HAVING COALESCE(SUM(i.cantidad), 0) > 0
    """)
    data = cursor.fetchall()

    productos = [d[0] for d in data]
    cantidades = [d[1] for d in data]

    alertas = [
        item for item in data
        if item[1] < cfg_prod.get(item[0], {}).get('umbral_alerta_dashboard', cfg['umbral_alerta_dashboard'])
    ]

    stock_bajo = len(alertas)

    # Resumen rápido: top 5 productos por cantidad (mayor > menor)
    resumen = sorted(data, key=lambda x: x[1], reverse=True)[:5]

    conn.close()

    return render_template(
        "dashboard.html",
        total=total,
        total_productos=total_productos,
        productos=productos,
        cantidades=cantidades,
        alertas=alertas,
        stock_bajo=stock_bajo,
        resumen=resumen
    )

from flask import request

@dashboard_bp.route("/reporte")
@login_required
def reporte():

    conn = conectar()
    cursor = conn.cursor()
    usuario_actual = session.get("user")
    rol_actual = session.get("rol")

    # 🔽 obtener filtros
    producto = request.args.get("producto")
    ubicacion = request.args.get("ubicacion")

    # 🔽 opciones para dropdown
    cursor.execute("SELECT nombre FROM productos")
    lista_productos = [p[0] for p in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT ubicacion FROM movimientos
        UNION
        SELECT DISTINCT piscina FROM inventario
    """)
    lista_ubicaciones = [u[0] for u in cursor.fetchall() if u[0]]

    # 🔽 query principal
    query = """
        SELECT p.nombre, COALESCE(i.piscina, 'Sin movimiento'), COALESCE(SUM(i.cantidad), 0)
        FROM productos p
        LEFT JOIN inventario i ON p.id = i.producto
        WHERE 1=1
    """

    params = []

    if producto:
        query += " AND p.nombre = %s"
        params.append(producto)

    if ubicacion:
        query += " AND i.piscina = %s"
        params.append(ubicacion)

    query += " GROUP BY p.nombre, i.piscina"

    cursor.execute(query, params)
    datos = cursor.fetchall()

    # Movimientos detallados (admin ve todos, otros usuarios solo los propios)
    mov_query = """
        SELECT COALESCE(p.nombre, m.producto), m.ubicacion, m.tipo, m.cantidad, m.fecha, m.usuario
        FROM movimientos m
        LEFT JOIN productos p ON p.id = m.producto
        WHERE 1=1
    """
    mov_params = []
    if rol_actual != "admin":
        mov_query += " AND m.usuario = %s"
        mov_params.append(usuario_actual)
    if producto:
        mov_query += " AND p.nombre = %s"
        mov_params.append(producto)
    if ubicacion:
        mov_query += " AND m.ubicacion = %s"
        mov_params.append(ubicacion)
    mov_query += " ORDER BY m.id DESC"

    cursor.execute(mov_query, mov_params)
    movimientos = cursor.fetchall()

    conn.close()

    return render_template(
        "reporte.html",
        reporte=datos,
        movimientos=movimientos,
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
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

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
    SELECT COALESCE(p.nombre, i.producto), i.piscina, SUM(i.cantidad)
    FROM inventario i
    LEFT JOIN productos p ON p.id = i.producto
    WHERE 1=1
    """

    params = []

    if producto:
        query += " AND p.nombre = %s"
        params.append(producto)

    if ubicacion:
        query += " AND i.piscina = %s"
        params.append(ubicacion)

    query += " GROUP BY COALESCE(p.nombre, i.producto), i.piscina"

    cursor.execute(query, params)
    datos = cursor.fetchall()

    # Movimientos para PDF (admin ve todos, otros usuarios solo los propios)
    usuario_actual = session.get("user", "")
    rol_actual = session.get("rol")
    mov_query = """
    SELECT COALESCE(p.nombre, m.producto), m.tipo, m.cantidad, m.ubicacion, m.fecha
    FROM movimientos m
    LEFT JOIN productos p ON p.id = m.producto
    WHERE 1=1
    """
    mov_params = []

    if rol_actual != "admin":
        mov_query += " AND m.usuario = %s"
        mov_params.append(usuario_actual)

    if producto:
        mov_query += " AND p.nombre = %s"
        mov_params.append(producto)

    if ubicacion:
        mov_query += " AND m.ubicacion = %s"
        mov_params.append(ubicacion)

    mov_query += " ORDER BY m.id DESC"

    cursor.execute(mov_query, mov_params)
    movimientos = cursor.fetchall()

    conn.close()

    # 📄 PDF
    pdf = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet()

    # Estilos adicionales empresariales
    styles.add(ParagraphStyle(name='HeadingEnterprise', fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=12, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='SubHeadingEnterprise', fontSize=12, leading=15, alignment=TA_CENTER, spaceAfter=18, fontName='Helvetica'))
    styles.add(ParagraphStyle(name='NormalJustify', fontSize=10, leading=14, alignment=TA_JUSTIFY, fontName='Helvetica'))
    styles.add(ParagraphStyle(name='MetaInfo', fontSize=9, leading=12, alignment=TA_LEFT, textColor=colors.grey))

    elementos = []

    # 🖼️ LOGO
    if os.path.exists("static/logo.png"):
        elementos.append(Image("static/logo.png", width=130, height=65))

    elementos.append(Spacer(1, 8))

    # 🏢 ENCABEZADO EMPRESARIAL
    elementos.append(Paragraph("AQUAMAX S.A.", styles['HeadingEnterprise']))
    elementos.append(Paragraph("REPORTE DE INVENTARIO", styles['SubHeadingEnterprise']))
    elementos.append(Paragraph("Empresa: AQUAMAX S.A. | Dirección: Av. Principal 1234 | Tel: (01) 234-5678", styles['MetaInfo']))

    # 📌 INFO AUDITORÍA
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    usuario = session.get("user", "Sistema")

    elementos.append(Paragraph(f"Código de reporte: {codigo_reporte}", styles['MetaInfo']))
    elementos.append(Paragraph(f"Generado por: {usuario}", styles['MetaInfo']))
    elementos.append(Paragraph(f"Fecha: {fecha}", styles['MetaInfo']))

    # 🔍 filtros visibles
    if producto:
        elementos.append(Paragraph(f"Filtro producto: {producto}", styles['MetaInfo']))
    if ubicacion:
        elementos.append(Paragraph(f"Filtro ubicación: {ubicacion}", styles['MetaInfo']))

    elementos.append(Spacer(1, 12))

    # 📊 TABLA
    tabla_data = [["Producto", "Ubicación", "Cantidad"]]

    for d in datos:
        tabla_data.append([str(d[0]), str(d[1]), f"{float(d[2]):.2f}"])

    colWidths = [220, 140, 80]
    tabla = Table(tabla_data, colWidths=colWidths, hAlign='LEFT')

    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#192a56")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('ALIGN',(0,0),(1,-1),'LEFT'),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor("#1f272d")),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9.5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#dcdde1")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,1),(-1,-1), colors.whitesmoke),
    ]))

    elementos.append(tabla)

    # 📜 TABLA MOVIMIENTOS DEL USUARIO
    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(f"MOVIMIENTOS DEL USUARIO: {usuario}", styles["Heading3"]))

    mov_data = [["Producto", "Tipo", "Cantidad", "Ubicacion", "Fecha"]]
    if movimientos:
        for m in movimientos:
            mov_data.append([str(m[0]), str(m[1]), str(m[2]), str(m[3]), str(m[4])])
    else:
        mov_data.append(["Sin movimientos", "-", "-", "-", "-"])

    mov_table = Table(mov_data, colWidths=[130, 80, 70, 90, 120], hAlign='LEFT')
    mov_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8.5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#dcdde1")),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
    ]))
    elementos.append(mov_table)

    # ✍️ FIRMA
    elementos.append(Spacer(1, 40))
    elementos.append(Paragraph("__________________________", styles["Normal"]))
    elementos.append(Paragraph("Firma responsable", styles["Normal"]))

    # 🏁 GENERAR
    pdf.build(elementos)

    return send_file(ruta_pdf, as_attachment=True)