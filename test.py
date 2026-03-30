import pytest
from app import app as flask_app
from database.db import insert_usuario, get_usuario, insert_producto, get_productos, insert_inventario, get_inventario, get_stock_actual
import os
from dotenv import load_dotenv

load_dotenv()

@pytest.fixture
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False  # Deshabilitar CSRF para tests
    with flask_app.app_context():
        yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

def test_home_page_redirect(client):
    response = client.get('/')
    assert response.status_code == 404  # No hay ruta raíz

def test_login_page(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data

def test_database_functions():
    # Limpiar tablas para test
    from database.db import conectar
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventario")
    cursor.execute("DELETE FROM productos")
    cursor.execute("DELETE FROM usuarios")
    conn.commit()
    conn.close()

    # Test usuario
    insert_usuario('testuser', 'hashedpass', 'user')
    user = get_usuario('testuser')
    assert user is not None
    assert user[1] == 'hashedpass'
    assert user[2] == 'user'

    # Test producto
    insert_producto('TEST001', 'Producto Test', 'Químico', '2024-01-01', 'testuser')
    productos = get_productos()
    assert len(productos) == 1
    assert productos[0][0] == 'TEST001'

    # Test inventario
    insert_inventario('TEST001', 10.0, 'GENERAL', '2024-01-01 12:00:00', 'testuser')
    inventario = get_inventario()
    assert len(inventario) == 1
    assert inventario[0][1] == 'TEST001'
    assert inventario[0][2] == 10.0

    # Test stock actual
    stock = get_stock_actual()
    assert len(stock) == 1
    assert stock[0][2] == 10.0

def test_inventario_access_without_login(client):
    response = client.get('/inventario')
    assert response.status_code == 302  # Redirect to login

def test_admin_creation():
    # Verificar que el admin se crea
    admin = get_usuario(os.getenv('ADMIN_USERNAME', 'admin'))
    assert admin is not None
    assert admin[2] == 'admin'

if __name__ == '__main__':
    pytest.main([__file__])