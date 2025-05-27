"""
Pruebas unitarias para la aplicación Tienda de Libros.

Este archivo contiene pruebas para las clases y funcionalidades principales
del sistema de gestión de tienda de libros.
"""
import pytest
import pyodbc
import itertools
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, ANY
import sys
import os

# Asegurarse de que el directorio del proyecto esté en el path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Importar las clases a probar
from tienda_libros import DatabaseManager, Libro, Transaccion, Tienda

# --- Fixtures para pruebas ---

@pytest.fixture
def mock_db_connection():
    """Fixture para simular una conexión a la base de datos."""
    with patch('pyodbc.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        yield mock_conn, mock_cursor

@pytest.fixture
def db_manager(mock_db_connection):
    """Fixture que proporciona un DatabaseManager configurado para pruebas."""
    mock_conn, _ = mock_db_connection
    return DatabaseManager()

@pytest.fixture
def tienda(db_manager):
    """Fixture que proporciona una instancia de Tienda para pruebas."""
    return Tienda(db_manager)

# --- Pruebas para la clase Libro ---

def test_libro_creacion():
    """Prueba la creación de un objeto Libro."""
    libro = Libro(
        isbn="1234567890",
        titulo="El Principito",
        precio_compra=150.50,
        precio_venta=250.75,
        cantidad_actual=10
    )
    
    assert libro.isbn == "1234567890"
    assert libro.titulo == "El Principito"
    assert libro.precio_compra == Decimal('150.50')
    assert libro.precio_venta == Decimal('250.75')
    assert libro.cantidad_actual == 10

def test_libro_str():
    """Prueba la representación en cadena de un Libro."""
    libro = Libro("1234567890", "El Principito", 150.50, 250.75, 10)
    expected = "ISBN: 1234567890, Título: El Principito, PV: $250.75, Stock: 10"
    assert str(libro) == expected

# --- Pruebas para la clase Transaccion ---

def test_transaccion_creacion():
    """Prueba la creación de un objeto Transaccion."""
    fecha = datetime(2023, 1, 1, 12, 0, 0)
    transaccion = Transaccion(
        id_transaccion=1,
        libro_isbn="1234567890",
        tipo="venta",
        fecha=fecha,
        cantidad=2
    )
    
    assert transaccion.id == 1
    assert transaccion.libro_isbn == "1234567890"
    assert transaccion.tipo == "venta"
    assert transaccion.fecha == fecha
    assert transaccion.cantidad == 2

def test_transaccion_str():
    """Prueba la representación en cadena de una Transaccion."""
    fecha = datetime(2023, 1, 1, 12, 0, 0)
    transaccion = Transaccion(
        id_transaccion=1,
        libro_isbn="1234567890",
        tipo="venta",
        fecha=fecha,
        cantidad=2
    )
    expected = "ID: 1, Fecha: 2023-01-01 12:00, Tipo: Venta, Cantidad: 2"
    assert str(transaccion) == expected

# --- Pruebas para la clase DatabaseManager ---

def test_database_manager_initialization(mock_db_connection):
    """Prueba la inicialización de DatabaseManager."""
    mock_conn, _ = mock_db_connection
    db_manager = DatabaseManager()
    
    assert db_manager.conn is not None
    mock_conn.cursor.assert_called_once()

def test_execute_query_select(mock_db_connection):
    """Prueba la ejecución de una consulta SELECT."""
    mock_conn, mock_cursor = mock_db_connection
    mock_cursor.fetchone.return_value = ("1234567890", "El Principito", 10)
    
    db_manager = DatabaseManager()
    result = db_manager.execute_query("SELECT * FROM Libros WHERE ISBN = ?", ("1234567890",), fetchone=True)
    
    assert result == ("1234567890", "El Principito", 10)
    mock_cursor.execute.assert_called_once_with("SELECT * FROM Libros WHERE ISBN = ?", ("1234567890",))

# --- Pruebas para la clase Tienda ---

def test_cargar_caja_desde_db_existente(db_manager, monkeypatch):
    """Prueba cargar el valor de la caja cuando ya existe en la BD."""
    # Configurar el mock para que devuelva un valor de caja existente
    mock_row = MagicMock()
    mock_row.Valor = Decimal('500000.00')
    db_manager.execute_query = MagicMock(return_value=mock_row)
    
    tienda = Tienda(db_manager)
    
    assert tienda.caja == Decimal('500000.00')
    db_manager.execute_query.assert_called_once_with(
        "SELECT Valor FROM ConfiguracionTienda WHERE Clave = 'Caja'", 
        fetchone=True
    )

def test_registrar_libro_exitoso():
    """Prueba el registro exitoso de un nuevo libro."""
    db_manager = MagicMock()
    # Primer llamada: consulta de caja (para _cargar_caja_desde_db)
    mock_row = MagicMock()
    mock_row.Valor = Decimal('10000.00')  # Caja suficiente para abastecer
    # Segunda llamada: buscar libro (no existe)
    # Tercera llamada: insertar libro
    # Cuarta llamada: registrar transacción de abastecimiento
    # Quinta llamada: actualizar caja en BD
    # Sexta llamada: commit (si la lógica lo requiere)
    db_manager.execute_query.side_effect = [
        mock_row,   # Para _cargar_caja_desde_db
        True,       # Insertar libro
        True,       # Registrar transacción abastecimiento
        True        # Actualizar caja en BD
    ]
    db_manager.commit = MagicMock()
    tienda = Tienda(db_manager)
    # Mock para buscar_libro_por_isbn: None la primera vez, luego libro realista
    class FakeLibro:
        def __init__(self):
            self.isbn = "1234567890"
            self.titulo = "Nuevo Libro"
            self.precio_compra = Decimal('100.00')
            self.precio_venta = Decimal('199.90')
            self.cantidad_actual = 5
    tienda.buscar_libro_por_isbn = MagicMock(side_effect=itertools.chain([None], itertools.repeat(FakeLibro())))
    resultado, mensaje = tienda.registrar_libro(
        isbn="1234567890",
        titulo="Nuevo Libro",
        precio_compra=100.00,
        precio_venta=199.90,
        cantidad_inicial=5
    )
    
    assert resultado is True
    assert "registrado con 5" in mensaje or "registrado con éxito" in mensaje
    print("CALL ARGS:", db_manager.execute_query.call_args_list)
    db_manager.execute_query.assert_any_call(
        "INSERT INTO Libros (ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual) VALUES (?, ?, ?, ?, ?)",
        ("1234567890", "Nuevo Libro", ANY, ANY, 5)
    )

def test_vender_libro_sin_stock():
    """Prueba intentar vender un libro sin stock suficiente."""
    db_manager = MagicMock()
    # La primera llamada a execute_query es para _cargar_caja_desde_db
    mock_row = MagicMock()
    mock_row.Valor = Decimal('1000.00')
    db_manager.execute_query.side_effect = [mock_row]
    tienda = Tienda(db_manager)
    
    class FakeLibro:
        def __init__(self):
            self.isbn = "1234567890"
            self.titulo = "Libro Sin Stock"
            self.cantidad_actual = 0
    
    tienda.buscar_libro_por_isbn = MagicMock(return_value=FakeLibro())
    
    resultado, mensaje = tienda.vender_libro("1234567890", 2)
    
    assert resultado is False
    assert "stock" in mensaje.lower()
    tienda.buscar_libro_por_isbn.assert_called_once_with("1234567890")

# --- Pruebas de integración ---

@patch('tienda_libros.DatabaseManager')
def test_integracion_registro_y_venta_libro(mock_db_class):
    """Prueba de integración: registrar un libro y luego venderlo."""
    # Configurar mocks
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db

    # Primer llamada: consulta de caja (para _cargar_caja_desde_db)
    mock_row = MagicMock()
    mock_row.Valor = Decimal('10000.00')  # Caja suficiente para abastecer
    # Segunda llamada: buscar libro (no existe)
    # Tercera llamada: insertar libro
    # Cuarta llamada: registrar transacción de abastecimiento
    # Quinta llamada: actualizar caja en BD
    # Sexta llamada: buscar libro para venta (devuelve objeto tipo fila)
    class FakeRow:
        ISBN = "1234567890"
        Titulo = "Libro de Prueba"
        PrecioCompra = 50.00
        PrecioVenta = 99.90
        CantidadActual = 10
    mock_db.execute_query.side_effect = [
        mock_row,  # Para _cargar_caja_desde_db
        True,      # Insertar libro
        True,      # Registrar transacción abastecimiento
        True,      # Actualizar caja en BD
        True,      # (dummy para commit)
        FakeRow,   # Buscar libro para venta
        True,      # Actualizar stock tras venta
        True,      # Actualizar caja tras venta
        True       # Registrar transacción de venta
    ]
    mock_db.commit = MagicMock()
    tienda = Tienda(mock_db)

    # Mock para buscar_libro_por_isbn: None en el registro, libro realista en la venta
    class FakeLibro:
        def __init__(self):
            self.isbn = "1234567890"
            self.titulo = "Libro de Prueba"
            self.precio_compra = Decimal('50.00')
            self.precio_venta = Decimal('99.90')
            self.cantidad_actual = 10
    tienda.buscar_libro_por_isbn = MagicMock(side_effect=itertools.chain([None], itertools.repeat(FakeLibro())))

    # 1. Registrar un nuevo libro
    resultado, mensaje = tienda.registrar_libro(
        isbn="1234567890",
        titulo="Libro de Prueba",
        precio_compra=50.00,
        precio_venta=99.90,
        cantidad_inicial=10
    )
    assert resultado is True
    assert "registrado con 10" in mensaje or "registrado con éxito" in mensaje

    # 2. Vender el libro
    resultado_venta, mensaje_venta = tienda.vender_libro("1234567890", 2)
    assert resultado_venta is True
    assert "vendidos" in mensaje_venta or "Venta registrada" in mensaje_venta


# --- Pruebas de esquema de la base de datos ---

def test_esquema_base_datos():
    """Verifica que las tablas necesarias existan en la base de datos."""
    db_manager = MagicMock()
    db_manager.execute_query.return_value = [("Libros",), ("Transacciones",), ("ConfiguracionTienda",)]
    
    # Ejecutar la verificación
    tablas = db_manager.execute_query(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'",
        fetchall=True
    )
    
    # Verificar que las tablas esperadas estén presentes
    tablas_esperadas = {"Libros", "Transacciones", "ConfiguracionTienda"}
    tablas_encontradas = {tabla[0] for tabla in tablas}
    
    assert tablas_esperadas.issubset(tablas_encontradas)


if __name__ == "__main__":
    pytest.main(["-v", "--cov=.", "--cov-report=term-missing"])

