from flask import Blueprint, render_template, request, session, redirect, flash
from database.db import conectar, get_productos, insert_inventario, get_inventario, get_stock_actual, get_stock_general_por_producto, get_configuracion_stock, get_configuracion_stock_producto_map_por_nombre, descontar_stock, insert_movimiento, get_movimientos_salida, get_ubicaciones
from datetime import datetime
import math
from routes.utils import login_required
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField
from wtforms.validators import DataRequired, NumberRange

inventario_bp = Blueprint('inventario', __name__)

class EntradaForm(FlaskForm):
    producto = SelectField('Producto', validators=[DataRequired()])
    cantidad = FloatField('Cantidad', validators=[DataRequired(), NumberRange(min=0.01)])

class SalidaForm(FlaskForm):
    producto = SelectField('Producto', validators=[DataRequired()])
    cantidad = FloatField('Cantidad', validators=[DataRequired(), NumberRange(min=0.01)])
    ubicacion = SelectField('Ubicación', choices=[], validators=[DataRequired()])

@inventario_bp.route('/inventario', methods=['GET','POST'])
@login_required
def inventario():
    entrada_form = EntradaForm()
    salida_form = SalidaForm()

    productos_db = get_productos()
    cfg = get_configuracion_stock()
    choices = [(p[0], p[1]) for p in productos_db]
    ubicaciones = get_ubicaciones()
    entrada_form.producto.choices = choices
    salida_form.producto.choices = choices
    salida_form.ubicacion.choices = [(u, u) for u in ubicaciones]

    if entrada_form.validate_on_submit():
        producto_id = entrada_form.producto.data
        cantidad = entrada_form.cantidad.data
        usuario = session.get('user')

        try:
            cantidad = float(cantidad)
        except (TypeError, ValueError):
            flash('Cantidad invalida. Ingresa un numero valido.', 'error')
            return redirect('/inventario')

        if not math.isfinite(cantidad) or cantidad <= 0:
            flash('Cantidad invalida. Debe ser mayor que 0.', 'error')
            return redirect('/inventario')

        if cantidad < cfg['min_cantidad_entrada']:
            flash(f'Cantidad invalida. Minimo permitido para entrada: {cfg["min_cantidad_entrada"]}', 'error')
            return redirect('/inventario')

        try:
            insert_inventario(producto_id, cantidad, 'GENERAL', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), usuario)
            insert_movimiento(producto_id, 'ENTRADA', cantidad, 'GENERAL', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), usuario)
            flash('Entrada registrada exitosamente', 'success')
        except Exception as e:
            flash(f'Error al registrar entrada: {str(e)}', 'error')

        return redirect('/inventario')

    stock_actual = get_stock_actual()
    umbrales_por_producto = get_configuracion_stock_producto_map_por_nombre()
    stock_general_map = get_stock_general_por_producto()
    if session.get('rol') == 'admin':
        retiros = get_movimientos_salida(10)
    else:
        retiros = get_movimientos_salida(10, session.get('user'))

    if session.get('rol') == 'admin':
        datos = get_inventario()
    else:
        datos = get_inventario(session['user'])

    return render_template(
        'inventario.html',
        datos=datos,
        stock_actual=stock_actual,
        productos=productos_db,
        entrada_form=entrada_form,
        salida_form=salida_form,
        retiros=retiros,
        stock_general_map=stock_general_map,
        umbral_critico=cfg['umbral_critico'],
        umbral_medio=cfg['umbral_medio'],
        min_salida=cfg['min_cantidad_salida'],
        umbrales_por_producto=umbrales_por_producto
    )

@inventario_bp.route('/salida', methods=['POST'])
@login_required
def salida():
    salida_form = SalidaForm()

    productos_db = get_productos()
    cfg = get_configuracion_stock()
    ubicaciones = get_ubicaciones()
    salida_form.producto.choices = [(p[0], p[1]) for p in productos_db]
    salida_form.ubicacion.choices = [(u, u) for u in ubicaciones]

    if salida_form.validate_on_submit():
        producto_id = salida_form.producto.data
        cantidad = salida_form.cantidad.data
        ubicacion = salida_form.ubicacion.data
        usuario = session.get('user')

        try:
            cantidad = float(cantidad)
        except (TypeError, ValueError):
            flash('Cantidad invalida. Ingresa un numero valido.', 'error')
            return redirect('/inventario')

        if not math.isfinite(cantidad) or cantidad <= 0:
            flash('Cantidad invalida. Debe ser mayor que 0.', 'error')
            return redirect('/inventario')

        if cantidad < cfg['min_cantidad_salida']:
            flash(f'Cantidad invalida. Minimo permitido para salida: {cfg["min_cantidad_salida"]}', 'error')
            return redirect('/inventario')

        conn = conectar()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(cantidad), 0) FROM inventario WHERE producto = %s AND piscina = 'GENERAL'",
            (producto_id,)
        )
        stock_general = float(cursor.fetchone()[0] or 0)
        conn.close()

        if stock_general < cantidad:
            flash(f'Stock insuficiente en GENERAL. Disponible: {stock_general}', 'error')
            return redirect('/inventario')

        try:
            descontar_stock(producto_id, cantidad, usuario)
            insert_movimiento(producto_id, 'SALIDA', cantidad, ubicacion, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), usuario)
            flash(f'Salida registrada exitosamente (destino: {ubicacion})', 'success')
        except Exception as e:
            flash(f'Error al registrar salida: {str(e)}', 'error')

    return redirect('/inventario')
