import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_inventario.db"

    monkeypatch.setenv("SECRET_KEY", "test_secret_key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "1234")
    monkeypatch.setenv("SUPERADMIN_USERNAME", "superadmin")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "1234")

    import app as app_module
    importlib.reload(app_module)

    app = app_module.app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
        yield client


def test_product_duplicate_name_is_blocked(app_client):
    client = app_client

    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["rol"] = "admin"

    r1 = client.post("/productos", data={"producto": "CLORO", "tipo": "ASEO"}, follow_redirects=True)
    assert r1.status_code == 200

    r2 = client.post("/productos", data={"producto": "cloro", "tipo": "ASEO"}, follow_redirects=True)
    assert r2.status_code == 200
    assert b"Ya existe un producto con ese nombre" in r2.data


def test_withdrawal_reduces_general_stock(app_client):
    client = app_client

    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["rol"] = "admin"

    client.post("/productos", data={"producto": "TRAPERO", "tipo": "ASEO"}, follow_redirects=True)

    # Obtener el ID del producto recien creado desde la pagina de productos
    page = client.get("/productos")
    html = page.data.decode("utf-8", errors="ignore")
    # Busca el primer codigo PRD- en la tabla
    start = html.find("PRD-")
    assert start != -1
    product_id = html[start:start + 12]

    client.post("/inventario", data={"producto": product_id, "cantidad": "100"}, follow_redirects=True)

    client.post("/salida", data={"producto": product_id, "cantidad": "30", "ubicacion": "Piscina"}, follow_redirects=True)

    inv_page = client.get("/inventario")
    inv_html = inv_page.data.decode("utf-8", errors="ignore")
    assert "Disponible en GENERAL: 70.0" in inv_html or "Disponible en GENERAL: 70" in inv_html


def test_non_admin_cannot_access_products(app_client):
    client = app_client

    with client.session_transaction() as sess:
        sess["user"] = "worker"
        sess["rol"] = "trabajador"

    r = client.get("/productos")
    assert r.status_code == 403
    assert b"Acceso denegado" in r.data
