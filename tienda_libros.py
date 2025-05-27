# --- Sección 1: Importaciones de Módulos ---
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import pyodbc # Para la conexión con SQL Server
from datetime import datetime
from decimal import Decimal, InvalidOperation # Para manejo preciso de moneda

# Para la API de portadas de OpenLibrary y manejo de imágenes
import requests # Para hacer peticiones HTTP
from PIL import Image, ImageTk # Pillow para manipulación de imágenes
import io # Para manejar bytes de imagen en memoria

# --- Sección 2: Configuración de la Conexión a la Base de Datos ---
DB_CONFIG = {
    'driver': '{SQL Server}',                 # Driver ODBC. Puede variar (ej. '{ODBC Driver 17 for SQL Server}')
    'server': r'Lorena\SQLEXPRESSV2',         # Nombre del servidor SQL Server (usar 'r' para raw string)
    'database': 'TiendaLibrosDB',             # Nombre de la base de datos creada
    'uid': 'sa',                              # Usuario de SQL Server
    'pwd': '26deabrilN*+@'                          # Contraseña del usuario SQL Server
    # 'trusted_connection': 'yes',            # Comentar o eliminar si se usa uid/pwd
}

# --- Sección 3: Clase DatabaseManager para la Gestión de la Base de Datos ---
def get_db_connection():
    """Establece y devuelve una conexión a la base de datos."""
    # Se configura autocommit=False para tener control explícito sobre las transacciones.
    conn_str = ';'.join(f'{k}={v}' for k, v in DB_CONFIG.items())
    try:
        conn = pyodbc.connect(conn_str, autocommit=False)
        print("Conexión a la base de datos establecida exitosamente.")
        return conn
    except pyodbc.Error as ex:
        messagebox.showerror("Error de Conexión a BD", f"No se pudo conectar a la base de datos:\n{ex}")
        return None

class DatabaseManager:
    """Clase para encapsular las operaciones de base de datos."""
    def __init__(self):
        self.conn = get_db_connection()
        if self.conn:
            self.cursor = self.conn.cursor()
        else:
            # Este error debería detener la app si la BD es esencial.
            raise ConnectionError("Fallo crítico al conectar con la base de datos durante la inicialización de DatabaseManager.")

    def execute_query(self, query, params=None, fetchone=False, fetchall=False, commit_flag=False):
        """
        Ejecuta una query.
        Si commit_flag es True, hace commit (para operaciones DML simples y autocontenidas como DELETE).
        Para transacciones complejas, el commit se maneja externamente llamando a self.commit().
        """
        if not self.conn or not self.cursor:
             messagebox.showerror("Error de BD", "No hay conexión activa a la base de datos.")
             return None if fetchone or fetchall else False
        try:
            self.cursor.execute(query, params or ())
            if commit_flag: # Para operaciones simples que necesitan commit inmediato
                self.conn.commit()
                return True # O self.cursor.rowcount > 0 si es relevante
            if fetchone:
                return self.cursor.fetchone()
            if fetchall:
                return self.cursor.fetchall()
            return self.cursor # Devolver cursor para rowcount u otras operaciones
        except pyodbc.Error as ex:
            # Si la query falla, se debería hacer rollback si la conexión no tiene autocommit.
            # El rollback se manejará en el método que llama a execute_query y controla la transacción.
            print(f"Error en execute_query (antes de rollback manual si aplica): {ex}")
            messagebox.showerror("Error de Query BD", f"Error al ejecutar query:\n{ex}\nQuery: {query}\nParams: {params}")
            return None if fetchone or fetchall else False # Indicar fallo

    def commit(self):
        """Realiza commit de la transacción actual."""
        if self.conn:
            try:
                self.conn.commit()
                print("Commit realizado en la base de datos.")
            except pyodbc.Error as e:
                messagebox.showerror("Error de Commit BD", f"No se pudo hacer commit: {e}")
                # Considerar relanzar la excepción para que el llamador la maneje
                raise

    def rollback(self):
        """Realiza rollback de la transacción actual."""
        if self.conn:
            try:
                self.conn.rollback()
                print("Rollback realizado en la base de datos.")
            except pyodbc.Error as e:
                messagebox.showerror("Error de Rollback BD", f"No se pudo hacer rollback: {e}")
                # Considerar relanzar

    def close(self):
        """Cierra la conexión a la base de datos."""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conn') and self.conn:
            try:
                # Si cerramos y hay transacciones pendientes sin commit, hacer rollback.
                if not self.conn.autocommit: # Verificamos si estaba en modo transaccional
                    # Esta llamada puede fallar si la conexión ya está en un estado problemático.
                    # self.conn.getinfo(pyodbc.SQL_ATTR_TXN_ISOLATION) # Una forma de chequear estado.
                    # Por simplicidad, intentamos rollback.
                    print("Cerrando conexión, intentando rollback de transacciones pendientes...")
                    self.conn.rollback() # Rollback de seguridad
            except pyodbc.Error as e:
                print(f"Error durante el rollback al cerrar la conexión: {e}")
            finally:
                self.conn.close()
                print("Conexión a la base de datos cerrada.")

# --- Sección 4: Clases de Negocio (Modelo de Datos) ---
class Transaccion:
    """Representa una transacción de venta o abastecimiento."""
    def __init__(self, tipo: str, cantidad: int, fecha: datetime = None, id_transaccion: int = None, libro_isbn: str = None):
        self.id = id_transaccion
        self.libro_isbn = libro_isbn
        self.tipo = tipo
        self.fecha = fecha if fecha else datetime.now()
        self.cantidad = cantidad

    def __str__(self):
        return (f"ID: {self.id or 'N/A'}, Fecha: {self.fecha.strftime('%Y-%m-%d %H:%M')}, "
                f"Tipo: {self.tipo.capitalize()}, Cantidad: {self.cantidad}")

class Libro:
    """Representa un libro del catálogo."""
    def __init__(self, isbn: str, titulo: str, precio_compra: float, precio_venta: float, cantidad_actual: int = 0):
        self.isbn = isbn
        self.titulo = titulo
        self.precio_compra = Decimal(str(precio_compra)) # Usar Decimal para precisión monetaria
        self.precio_venta = Decimal(str(precio_venta))
        self.cantidad_actual = cantidad_actual
        self.total_vendido_consulta = 0 # Usado por la función de "más vendido"

    def __str__(self): # Usado en listados simples en la GUI
        return f"ISBN: {self.isbn}, Título: {self.titulo}, PV: ${self.precio_venta:,.2f}, Stock: {self.cantidad_actual}"

class Tienda:
    """Clase principal para la lógica de negocio de la tienda."""
    def __init__(self, db_manager: DatabaseManager, inversion_inicial_default: float = 1000000.00):
        self.db = db_manager
        self.caja = Decimal('0.0') # Se inicializa y luego se carga desde la BD
        self._cargar_caja_desde_db(Decimal(str(inversion_inicial_default)))

    def _cargar_caja_desde_db(self, valor_por_defecto_si_no_existe: Decimal):
        """Carga el valor de la caja desde la BD. Si no existe, lo crea."""
        query = "SELECT Valor FROM ConfiguracionTienda WHERE Clave = 'Caja'"
        row = self.db.execute_query(query, fetchone=True) # No necesita commit
        if row:
            self.caja = Decimal(row.Valor)
            print(f"Caja cargada desde BD: ${self.caja:,.2f}")
        else:
            # La clave 'Caja' no existe, la insertamos con el valor por defecto
            self.caja = valor_por_defecto_si_no_existe
            insert_query = "INSERT INTO ConfiguracionTienda (Clave, Valor) VALUES ('Caja', ?)"
            # Esta es una operación de escritura y necesita commit.
            if self.db.execute_query(insert_query, (self.caja,), commit_flag=True):
                print(f"Clave 'Caja' no encontrada. Inicializada en BD con: ${self.caja:,.2f}")
            else:
                # Falló la inserción, usar valor en memoria y advertir
                messagebox.showwarning("Advertencia Caja",
                                       f"No se pudo inicializar 'Caja' en la BD. Usando valor en memoria: ${self.caja:,.2f}")
        if self.caja is None: # Salvaguarda por si algo sale muy mal
            self.caja = Decimal('0.0')

    def _actualizar_caja_en_db(self):
        """
        Prepara la query para actualizar la caja en BD.
        NO hace commit aquí; el commit es manejado por el método que orquesta la transacción.
        Lanza una excepción si la query falla, para que la transacción haga rollback.
        """
        query = "UPDATE ConfiguracionTienda SET Valor = ? WHERE Clave = 'Caja'"
        if not self.db.execute_query(query, (self.caja,)): # Sin commit_flag
            raise Exception("Fallo al preparar la actualización de la caja en la base de datos.")

    def _registrar_transaccion_db(self, isbn: str, tipo: str, cantidad: int, fecha: datetime = None):
        """
        Prepara la query para registrar una transacción.
        NO hace commit aquí; el commit es manejado por el método que orquesta la transacción.
        Lanza una excepción si la query falla.
        """
        query = "INSERT INTO Transacciones (LibroISBN, TipoTransaccion, Cantidad, FechaTransaccion) VALUES (?, ?, ?, ?)"
        params = (isbn, tipo, cantidad, fecha if fecha else datetime.now())
        if not self.db.execute_query(query, params): # Sin commit_flag
            raise Exception("Fallo al preparar el registro de la transacción en la base de datos.")

    # --- Métodos de Operaciones Principales (con manejo de transacciones) ---
    def registrar_libro(self, isbn: str, titulo: str, precio_compra: float, precio_venta: float, cantidad_inicial: int = 0):
        if self.buscar_libro_por_isbn(isbn): # Búsqueda no necesita transacción explícita
            return False, f"Error: El ISBN '{isbn}' ya existe."
        
        original_caja_val = self.caja # Para revertir en memoria si falla
        try:
            query_libro = "INSERT INTO Libros (ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual) VALUES (?, ?, ?, ?, ?)"
            params_libro = (isbn, titulo, Decimal(str(precio_compra)), Decimal(str(precio_venta)), cantidad_inicial)
            if not self.db.execute_query(query_libro, params_libro):
                raise Exception("Error al insertar el libro en la tabla Libros.")

            mensaje_final = f"Libro '{titulo}' registrado con {cantidad_inicial} ejemplares."
            
            if cantidad_inicial > 0:
                costo_abastecimiento = Decimal(str(precio_compra)) * cantidad_inicial
                if self.caja >= costo_abastecimiento:
                    self.caja -= costo_abastecimiento # Modifica caja en memoria
                    self._actualizar_caja_en_db()     # Prepara query para actualizar caja en BD
                    self._registrar_transaccion_db(isbn, "abastecimiento", cantidad_inicial) # Prepara query de transacción
                    mensaje_final += f" Costo: ${costo_abastecimiento:,.2f}. Caja actual: ${self.caja:,.2f}"
                else:
                    # No hay caja suficiente, el libro se registra con 0 stock.
                    # Si el INSERT inicial puso cantidad_inicial > 0, hay que corregirlo.
                    if not self.db.execute_query("UPDATE Libros SET CantidadActual = 0 WHERE ISBN = ?", (isbn,)):
                         raise Exception("Fallo al actualizar stock a 0 del libro por falta de caja.")
                    mensaje_final = (f"Libro '{titulo}' registrado. Stock inicial no abastecido por falta de caja (${self.caja:,.2f}). Cantidad establecida a 0.")
            
            self.db.commit() # Si todo fue bien, hacer commit de todas las operaciones.
            return True, mensaje_final
        except Exception as e:
            self.db.rollback() # Revertir todas las operaciones en la BD
            self.caja = original_caja_val # Revertir caja en memoria
            return False, f"Error registrando libro: {e}"

    def eliminar_libro(self, isbn: str):
        """Elimina un libro. Esta es una operación simple que puede usar commit_flag."""
        if not self.buscar_libro_por_isbn(isbn):
            return False, f"Error: El libro con ISBN '{isbn}' no existe."
        # ON DELETE CASCADE en la FK se encarga de las transacciones asociadas.
        if self.db.execute_query("DELETE FROM Libros WHERE ISBN = ?", (isbn,), commit_flag=True):
            return True, f"Libro con ISBN '{isbn}' y sus transacciones eliminados."
        # Si execute_query devolvió False, el error ya se mostró en messagebox
        return False, f"Error al intentar eliminar el libro ISBN '{isbn}' (verifique mensajes anteriores)."


    def abastecer_libro(self, isbn: str, cantidad: int):
        libro = self.buscar_libro_por_isbn(isbn)
        if not libro: return False, f"Error: Libro ISBN '{isbn}' no existe."
        if cantidad <= 0: return False, "Cantidad a abastecer debe ser positiva."
        
        costo = libro.precio_compra * cantidad
        if self.caja < costo: return False, f"Caja insuficiente (${self.caja:,.2f}). Costo de abastecimiento: ${costo:,.2f}"
        
        original_caja_val = self.caja
        try:
            nueva_cantidad_stock = libro.cantidad_actual + cantidad
            if not self.db.execute_query("UPDATE Libros SET CantidadActual = ? WHERE ISBN = ?", (nueva_cantidad_stock, isbn)):
                raise Exception("Fallo al actualizar el stock del libro.")
            
            self.caja -= costo # Actualizar caja en memoria
            self._actualizar_caja_en_db() # Preparar query para actualizar caja en BD
            self._registrar_transaccion_db(isbn, "abastecimiento", cantidad) # Preparar query para registrar transacción
            
            self.db.commit() # Si todo ok, commit todas las operaciones.
            return True, f"{cantidad} ejemplares de '{libro.titulo}' abastecidos. Costo: ${costo:,.2f}. Caja actual: ${self.caja:,.2f}"
        except Exception as e:
            self.db.rollback() # Revertir operaciones en BD
            self.caja = original_caja_val # Revertir caja en memoria
            return False, f"Error en la operación de abastecimiento: {e}"

    def vender_libro(self, isbn: str, cantidad: int):
        libro = self.buscar_libro_por_isbn(isbn)
        if not libro: return False, f"Error: Libro ISBN '{isbn}' no existe."
        if cantidad <= 0: return False, "Cantidad a vender debe ser positiva."
        if libro.cantidad_actual < cantidad: return False, f"Stock insuficiente ({libro.cantidad_actual}). Solicitados: {cantidad}"
        
        original_caja_val = self.caja
        try:
            nueva_cantidad_stock = libro.cantidad_actual - cantidad
            if not self.db.execute_query("UPDATE Libros SET CantidadActual = ? WHERE ISBN = ?", (nueva_cantidad_stock, isbn)):
                raise Exception("Fallo al actualizar el stock del libro.")

            ingreso_venta = libro.precio_venta * cantidad
            self.caja += ingreso_venta # Actualizar caja en memoria
            self._actualizar_caja_en_db() # Preparar query para actualizar caja en BD
            self._registrar_transaccion_db(isbn, "venta", cantidad) # Preparar query para registrar transacción
            
            self.db.commit() # Si todo ok, commit todas las operaciones.
            return True, f"{cantidad} ejemplares de '{libro.titulo}' vendidos. Ingreso: ${ingreso_venta:,.2f}. Caja actual: ${self.caja:,.2f}"
        except Exception as e:
            self.db.rollback() # Revertir operaciones en BD
            self.caja = original_caja_val # Revertir caja en memoria
            return False, f"Error en la operación de venta: {e}"

    # --- Métodos de Consulta (generalmente no modifican datos, no necesitan transacciones complejas) ---
    def buscar_libro_por_isbn(self, isbn: str) -> Libro | None:
        row = self.db.execute_query("SELECT ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual FROM Libros WHERE ISBN = ?", (isbn,), fetchone=True)
        if row: return Libro(row.ISBN, row.Titulo, float(row.PrecioCompra), float(row.PrecioVenta), row.CantidadActual)
        return None

    def buscar_libros_por_titulo(self, titulo_parcial: str) -> list[Libro]:
        rows = self.db.execute_query("SELECT ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual FROM Libros WHERE Titulo LIKE ?", (f'%{titulo_parcial}%',), fetchall=True)
        return [Libro(r.ISBN, r.Titulo, float(r.PrecioCompra), float(r.PrecioVenta), r.CantidadActual) for r in rows] if rows else []

    def calcular_transacciones_abastecimiento(self, isbn: str) -> tuple[bool, str | int]:
        if not self.buscar_libro_por_isbn(isbn): return False, f"Libro ISBN '{isbn}' no existe."
        row = self.db.execute_query("SELECT COUNT(*) FROM Transacciones WHERE LibroISBN = ? AND TipoTransaccion = 'abastecimiento'", (isbn,), fetchone=True)
        return (True, row[0]) if row else (False, "Error al calcular transacciones de abastecimiento.")

    def buscar_libro_mas_costoso(self) -> Libro | None:
        row = self.db.execute_query("SELECT TOP 1 ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual FROM Libros ORDER BY PrecioVenta DESC", fetchone=True)
        if row: return Libro(row.ISBN, row.Titulo, float(row.PrecioCompra), float(row.PrecioVenta), row.CantidadActual)
        return None

    def buscar_libro_menos_costoso(self) -> Libro | None:
        row = self.db.execute_query("SELECT TOP 1 ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual FROM Libros ORDER BY PrecioVenta ASC", fetchone=True)
        if row: return Libro(row.ISBN, row.Titulo, float(row.PrecioCompra), float(row.PrecioVenta), row.CantidadActual)
        return None

    def buscar_libro_mas_vendido(self) -> Libro | None:
        query = """
            SELECT TOP 1 L.ISBN, L.Titulo, L.PrecioCompra, L.PrecioVenta, L.CantidadActual, SUM(T.Cantidad) as TotalVendido
            FROM Libros L JOIN Transacciones T ON L.ISBN = T.LibroISBN
            WHERE T.TipoTransaccion = 'venta'
            GROUP BY L.ISBN, L.Titulo, L.PrecioCompra, L.PrecioVenta, L.CantidadActual
            HAVING SUM(T.Cantidad) > 0 -- Asegurarse de que haya al menos una venta
            ORDER BY TotalVendido DESC
        """
        row = self.db.execute_query(query, fetchone=True)
        if row:
            libro = Libro(row.ISBN, row.Titulo, float(row.PrecioCompra), float(row.PrecioVenta), row.CantidadActual)
            libro.total_vendido_consulta = row.TotalVendido # Guardar el total para mostrarlo
            return libro
        return None

    def obtener_catalogo_completo(self) -> list[Libro]:
        rows = self.db.execute_query("SELECT ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual FROM Libros ORDER BY Titulo", fetchall=True)
        return [Libro(r.ISBN, r.Titulo, float(r.PrecioCompra), float(r.PrecioVenta), r.CantidadActual) for r in rows] if rows else []

    def obtener_transacciones_de_libro(self, isbn: str) -> list[Transaccion]:
        rows = self.db.execute_query("SELECT ID, LibroISBN, TipoTransaccion, FechaTransaccion, Cantidad FROM Transacciones WHERE LibroISBN = ? ORDER BY FechaTransaccion DESC", (isbn,), fetchall=True)
        return [Transaccion(r.TipoTransaccion, r.Cantidad, r.FechaTransaccion, r.ID, r.LibroISBN) for r in rows] if rows else []

# --- Sección 5: Clase de la Interfaz Gráfica (GUI) con Tkinter ---
class TiendaLibrosApp:
    """Clase principal de la aplicación GUI."""
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Sistema de Gestión - Tienda de Libros")
        self.root.geometry("1050x700") # Ancho x Alto

        # Inicializar DatabaseManager y Tienda. Manejar errores críticos aquí.
        try:
            self.db_manager = DatabaseManager()
            self.tienda = Tienda(self.db_manager) # Tienda ahora carga la caja desde BD
        except ConnectionError as e:
            # Este error ya es manejado por DatabaseManager mostrando un messagebox.
            # Aquí solo nos aseguramos de que la app no continúe.
            print(f"Error crítico de conexión al inicializar TiendaLibrosApp: {e}")
            self.root.destroy() # Cerrar la ventana principal si la BD no está disponible.
            return # Detener la inicialización de la GUI.
        except Exception as e_init:
            messagebox.showerror("Error Crítico de Inicialización", f"Ocurrió un error al inicializar la tienda: {e_init}\nLa aplicación se cerrará.")
            if hasattr(self, 'db_manager') and self.db_manager:
                self.db_manager.close() # Intentar cerrar la conexión si se abrió
            self.root.destroy()
            return

        self.current_cover_photo = None # Para mantener referencia a la imagen de portada

        self.setup_ui() # Configurar los widgets de la GUI
        self.actualizar_estado_caja_label() # Mostrar el saldo inicial de la caja
        self.gui_mostrar_catalogo_completo() # Cargar y mostrar el catálogo al iniciar

    def setup_ui(self):
        """Configura los elementos visuales de la interfaz gráfica."""
        # Usar PanedWindow para dividir la ventana en secciones redimensionables
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Panel izquierdo: Controles y Treeview del catálogo
        left_pane = ttk.Frame(main_pane, width=750) # Darle un ancho inicial
        main_pane.add(left_pane, weight=3) # Más peso para que ocupe más espacio al redimensionar

        # --- Contenedor para botones de operaciones ---
        control_frame = ttk.LabelFrame(left_pane, text="Operaciones Principales", padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        # Fila 1 de botones
        btn_row1_frame = ttk.Frame(control_frame)
        btn_row1_frame.pack(fill=tk.X, pady=2)
        ttk.Button(btn_row1_frame, text="Registrar Libro", command=self.gui_registrar_libro).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        ttk.Button(btn_row1_frame, text="Eliminar Libro", command=self.gui_eliminar_libro).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        # Fila 2 de botones
        btn_row2_frame = ttk.Frame(control_frame)
        btn_row2_frame.pack(fill=tk.X, pady=2)
        ttk.Button(btn_row2_frame, text="Abastecer Libro", command=self.gui_abastecer_libro).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        ttk.Button(btn_row2_frame, text="Vender Libro", command=self.gui_vender_libro).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # --- Contenedor para botones de consultas ---
        query_frame = ttk.LabelFrame(left_pane, text="Consultas y Búsquedas", padding="10")
        query_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        # Fila 1 de consultas
        query_row1_frame = ttk.Frame(query_frame)
        query_row1_frame.pack(fill=tk.X, pady=2)
        ttk.Button(query_row1_frame, text="Buscar por ISBN", command=self.gui_buscar_por_isbn).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        ttk.Button(query_row1_frame, text="Buscar por Título", command=self.gui_buscar_por_titulo).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        # Fila 2 de consultas
        query_row2_frame = ttk.Frame(query_frame)
        query_row2_frame.pack(fill=tk.X, pady=2)
        ttk.Button(query_row2_frame, text="Libro Más Costoso", command=lambda: self.gui_mostrar_libro_especial("costoso")).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(query_row2_frame, text="Libro Menos Costoso", command=lambda: self.gui_mostrar_libro_especial("barato")).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(query_row2_frame, text="Libro Más Vendido", command=lambda: self.gui_mostrar_libro_especial("mas_vendido")).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(query_row2_frame, text="Trans. Abastecimiento", command=self.gui_transacciones_abastecimiento_libro).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        # --- Contenedor para el Treeview (Catálogo) ---
        catalog_display_frame = ttk.LabelFrame(left_pane, text="Catálogo de Libros / Resultados de Búsqueda", padding="10")
        catalog_display_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tree_catalogo = ttk.Treeview(catalog_display_frame, columns=("ISBN", "Titulo", "P. Venta", "Stock"), show="headings")
        self.tree_catalogo.heading("ISBN", text="ISBN"); self.tree_catalogo.column("ISBN", width=130, anchor=tk.W, minwidth=100)
        self.tree_catalogo.heading("Titulo", text="Título"); self.tree_catalogo.column("Titulo", width=350, anchor=tk.W, minwidth=200)
        self.tree_catalogo.heading("P. Venta", text="P.Venta"); self.tree_catalogo.column("P. Venta", width=90, anchor=tk.E, minwidth=70)
        self.tree_catalogo.heading("Stock", text="Stock"); self.tree_catalogo.column("Stock", width=70, anchor=tk.CENTER, minwidth=50)

        tree_scrollbar = ttk.Scrollbar(catalog_display_frame, orient=tk.VERTICAL, command=self.tree_catalogo.yview)
        self.tree_catalogo.configure(yscrollcommand=tree_scrollbar.set)
        self.tree_catalogo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Eventos del Treeview
        self.tree_catalogo.bind("<Double-1>", self.on_tree_catalogo_double_click) # Doble clic para ver detalles
        self.tree_catalogo.bind("<ButtonRelease-1>", self.on_tree_catalogo_single_click) # Clic para mostrar portada

        # Botón para refrescar/mostrar catálogo completo
        ttk.Button(left_pane, text="Mostrar Catálogo Completo / Refrescar", command=self.gui_mostrar_catalogo_completo).pack(side=tk.TOP, pady=(5,0), padx=10, fill=tk.X)

        # Etiqueta para mostrar el saldo de la caja
        self.caja_status_label = ttk.Label(left_pane, text="Caja: $0.00", font=("Arial", 12, "bold"), anchor=tk.E)
        self.caja_status_label.pack(side=tk.BOTTOM, pady=10, padx=10, fill=tk.X)

        # Panel derecho: Visualización de la portada del libro
        right_pane = ttk.Frame(main_pane, width=300) # Ancho inicial para la portada
        main_pane.add(right_pane, weight=1) # Menos peso

        cover_display_frame = ttk.LabelFrame(right_pane, text="Portada del Libro", padding="10")
        cover_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.cover_image_display_label = ttk.Label(cover_display_frame, text="Seleccione un libro del catálogo para ver su portada.", anchor=tk.CENTER, justify=tk.CENTER, wraplength=250)
        self.cover_image_display_label.pack(padx=5, pady=5, expand=True, fill=tk.BOTH)

    # --- Métodos Auxiliares de la GUI ---
    def actualizar_estado_caja_label(self):
        """Actualiza la etiqueta que muestra el saldo de la caja."""
        if hasattr(self, 'tienda') and self.tienda: # Verificar que tienda esté inicializada
             self.caja_status_label.config(text=f"Caja Actual: ${self.tienda.caja:,.2f}")
        else: # Caso de error donde tienda no se pudo inicializar
             self.caja_status_label.config(text="Caja: (Error de inicialización)")

    def limpiar_treeview_catalogo(self):
        """Elimina todos los items del Treeview del catálogo."""
        for item in self.tree_catalogo.get_children():
            self.tree_catalogo.delete(item)

    def poblar_treeview_catalogo(self, libros: list[Libro]):
        """Llena el Treeview del catálogo con la lista de libros proporcionada."""
        self.limpiar_treeview_catalogo()
        for libro in libros:
            pv_formatted = f"${libro.precio_venta:,.2f}" # Formatear precio venta
            self.tree_catalogo.insert("", tk.END, values=(libro.isbn, libro.titulo, pv_formatted, libro.cantidad_actual), iid=libro.isbn) # Usar ISBN como iid

    def gui_mostrar_catalogo_completo(self):
        """Carga y muestra todos los libros del catálogo."""
        catalogo = self.tienda.obtener_catalogo_completo()
        self.poblar_treeview_catalogo(catalogo)
        if not catalogo:
            messagebox.showinfo("Catálogo Vacío", "El catálogo de libros está actualmente vacío.")
        # Limpiar la visualización de la portada al refrescar el catálogo
        self.cover_image_display_label.config(text="Seleccione un libro del catálogo para ver su portada.", image=None)
        self.current_cover_photo = None # Liberar referencia a la imagen anterior

    # --- Manejadores de Eventos del Treeview ---
    def on_tree_catalogo_single_click(self, event):
        """Manejador para un solo clic en el Treeview: muestra la portada del libro seleccionado."""
        selected_item_iid = self.tree_catalogo.focus() # Obtiene el IID (ISBN) del item seleccionado
        if not selected_item_iid: return # Si no hay nada seleccionado, no hacer nada

        # item_values = self.tree_catalogo.item(selected_item_iid, "values") # No necesitamos los valores aquí, solo el ISBN (iid)
        # if item_values and len(item_values) > 0:
        #     isbn = item_values[0]
        self.gui_mostrar_portada_libro_api(selected_item_iid) # Pasar el ISBN directamente

    def on_tree_catalogo_double_click(self, event):
        """Manejador para doble clic en el Treeview: muestra detalles y transacciones del libro."""
        selected_item_iid = self.tree_catalogo.focus()
        if not selected_item_iid: return

        # item_values = self.tree_catalogo.item(selected_item_iid, "values")
        # if item_values and len(item_values) > 0:
        #     isbn = item_values[0]
        self.gui_ver_detalle_libro_popup(selected_item_iid)
        # La portada ya se actualiza con el single_click si el usuario hizo clic antes del doble clic.

    # --- Lógica para Mostrar Portada (API OpenLibrary) ---
    def gui_mostrar_portada_libro_api(self, isbn: str):
        """Obtiene y muestra la portada de un libro usando la API de OpenLibrary."""
        self.cover_image_display_label.config(text=f"Buscando portada para {isbn}...", image=None)
        self.current_cover_photo = None # Limpiar imagen anterior
        self.cover_image_display_label.image = None # Limpiar referencia
        self.root.update_idletasks() # Forzar actualización de la UI para mostrar "Buscando..."

        try:
            # API de OpenLibrary Covers: M (Mediana), S (Pequeña), L (Grande)
            # default=false para no obtener una imagen genérica si no hay portada específica
            url = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
            response = requests.get(url, stream=True, timeout=8) # Timeout un poco más largo

            if response.status_code == 200 and 'image' in response.headers.get('Content-Type', '').lower():
                image_bytes = response.content
                # Heurística simple para verificar si es una imagen válida y no un placeholder pequeño
                if not image_bytes or len(image_bytes) < 200: # Umbral bajo, ajustar si es necesario
                    raise ValueError("La imagen recibida parece ser un placeholder o inválida.")

                img = Image.open(io.BytesIO(image_bytes))

                # Redimensionar la imagen para que quepa en el label de portada
                label_width = self.cover_image_display_label.winfo_width()
                label_height = self.cover_image_display_label.winfo_height()
                # Si el label aún no tiene dimensiones (ej. al inicio), usar valores por defecto
                if label_width < 20 or label_height < 20:
                    label_width, label_height = 250, 350 # Valores por defecto para redimensionar

                img.thumbnail((label_width - 20, label_height - 20), Image.Resampling.LANCZOS) # Dejar un pequeño margen

                self.current_cover_photo = ImageTk.PhotoImage(img)
                self.cover_image_display_label.config(image=self.current_cover_photo, text="") # Mostrar imagen, borrar texto
                self.cover_image_display_label.image = self.current_cover_photo # Guardar referencia
            else:
                self.cover_image_display_label.config(text="Portada no disponible.", image=None)
        except requests.exceptions.Timeout:
            print(f"Timeout al obtener portada para ISBN: {isbn}")
            self.cover_image_display_label.config(text="Timeout al cargar portada.", image=None)
        except requests.exceptions.RequestException as e:
            print(f"Error de red al obtener portada para ISBN {isbn}: {e}")
            self.cover_image_display_label.config(text="Error de red al cargar portada.", image=None)
        except (Image.UnidentifiedImageError, ValueError, Exception) as e: # Capturar errores de Pillow o imagen inválida
            print(f"Error procesando imagen para ISBN {isbn}: {e}")
            self.cover_image_display_label.config(text="Portada no válida o error de procesamiento.", image=None)

    # --- Métodos GUI para Operaciones de la Tienda (Ventanas Emergentes y Lógica) ---
    def gui_registrar_libro(self):
        """Muestra un formulario para registrar un nuevo libro."""
        # Crear una ventana Toplevel para el formulario
        form_window = tk.Toplevel(self.root)
        form_window.title("Registrar Nuevo Libro")
        form_window.geometry("450x280") # Ajustar tamaño
        form_window.transient(self.root) # Hacerla modal sobre la principal
        form_window.grab_set() # Capturar eventos para esta ventana

        fields = ["ISBN:", "Título:", "Precio Compra ($):", "Precio Venta ($):", "Cantidad Inicial:"]
        entries = {} # Diccionario para almacenar los widgets de entrada

        form_frame = ttk.Frame(form_window, padding="15")
        form_frame.pack(expand=True, fill=tk.BOTH)

        for i, field_text in enumerate(fields):
            ttk.Label(form_frame, text=field_text).grid(row=i, column=0, padx=5, pady=8, sticky=tk.W)
            entry_widget = ttk.Entry(form_frame, width=35)
            entry_widget.grid(row=i, column=1, padx=5, pady=8, sticky=tk.EW)
            # Usar una clave simple para el diccionario de entries
            entries[field_text.split(":")[0].replace(" ($)", "").replace(" ", "_").lower()] = entry_widget
        
        entries["cantidad_inicial"].insert(0, "0") # Valor por defecto para cantidad

        def on_submit_registro():
            try:
                isbn = entries["isbn"].get().strip()
                titulo = entries["título"].get().strip()
                # Validar y convertir precios y cantidad
                try:
                    precio_compra = float(entries["precio_compra"].get())
                    precio_venta = float(entries["precio_venta"].get())
                    cantidad_inicial = int(entries["cantidad_inicial"].get())
                except ValueError:
                    messagebox.showerror("Error de Formato", "Precio compra, precio venta y cantidad deben ser números válidos.", parent=form_window)
                    return

                if not isbn or not titulo:
                    messagebox.showerror("Error de Validación", "ISBN y Título no pueden estar vacíos.", parent=form_window)
                    return
                if precio_compra < 0 or precio_venta < 0 or cantidad_inicial < 0:
                     messagebox.showerror("Error de Validación", "Los valores numéricos (precios, cantidad) no pueden ser negativos.", parent=form_window)
                     return

                exito, msg = self.tienda.registrar_libro(isbn, titulo, precio_compra, precio_venta, cantidad_inicial)
                if exito:
                    messagebox.showinfo("Registro Exitoso", msg, parent=form_window)
                    self.actualizar_estado_caja_label()
                    self.gui_mostrar_catalogo_completo() # Refrescar vista principal
                    form_window.destroy() # Cerrar ventana de formulario
                else:
                    messagebox.showerror("Error de Registro", msg, parent=form_window)
            except Exception as e_submit: # Capturar cualquier otro error inesperado
                messagebox.showerror("Error Inesperado", f"Ocurrió un error: {e_submit}", parent=form_window)

        submit_button = ttk.Button(form_frame, text="Registrar Libro", command=on_submit_registro)
        submit_button.grid(row=len(fields), column=0, columnspan=2, pady=(15,5), ipady=5) # Botón más grande
        
        form_frame.columnconfigure(1, weight=1) # Hacer que la columna de entries se expanda
        form_window.wait_window() # Esperar a que esta ventana se cierre antes de continuar

    def gui_eliminar_libro(self):
        """Solicita ISBN y elimina el libro correspondiente."""
        # Obtener ISBN del libro seleccionado en el Treeview, si hay alguno
        selected_item_iid = self.tree_catalogo.focus()
        initial_isbn = ""
        if selected_item_iid:
            initial_isbn = selected_item_iid # El IID es el ISBN

        isbn = simpledialog.askstring("Eliminar Libro", "Ingrese el ISBN del libro a eliminar:", initialvalue=initial_isbn, parent=self.root)
        if isbn: # Si el usuario ingresó un ISBN y no canceló
            if messagebox.askyesno("Confirmar Eliminación", f"¿Está seguro de que desea eliminar el libro con ISBN '{isbn}' y todas sus transacciones asociadas?", icon='warning', parent=self.root):
                exito, msg = self.tienda.eliminar_libro(isbn)
                messagebox.showinfo("Resultado de Eliminación", msg) # Mostrar resultado
                if exito:
                    self.gui_mostrar_catalogo_completo() # Refrescar catálogo
                    # Limpiar portada si el libro eliminado era el que se mostraba
                    self.cover_image_display_label.config(text="Seleccione un libro...", image=None)
                    self.current_cover_photo = None

    def _ask_isbn_and_cantidad(self, title: str, prompt_libro: str, prompt_cantidad: str, libro_info: Libro | None = None):
        """Función auxiliar para solicitar ISBN y cantidad."""
        isbn = simpledialog.askstring(title, prompt_libro, initialvalue=libro_info.isbn if libro_info else "", parent=self.root)
        if not isbn: return None, None # Usuario canceló ISBN

        # Validar que el libro exista antes de pedir cantidad (opcional, pero mejora UX)
        libro_actual = self.tienda.buscar_libro_por_isbn(isbn)
        if not libro_actual:
            messagebox.showerror("Error", f"Libro con ISBN '{isbn}' no encontrado.", parent=self.root)
            return None, None
        
        info_extra = f"\nLibro: {libro_actual.titulo}"
        if "Stock" in prompt_cantidad: info_extra += f"\nStock Actual: {libro_actual.cantidad_actual}"
        if "PV" in prompt_cantidad: info_extra += f"\nPrecio Venta: ${libro_actual.precio_venta:,.2f}"

        cantidad_str = simpledialog.askstring(title, f"{prompt_cantidad}{info_extra}\n\nIngrese la cantidad:", parent=self.root)
        if not cantidad_str: return isbn, None # Usuario canceló cantidad

        try:
            cantidad = int(cantidad_str)
            if cantidad <= 0:
                messagebox.showerror("Error de Validación", "La cantidad debe ser un número entero positivo.", parent=self.root)
                return isbn, None
            return isbn, cantidad
        except ValueError:
            messagebox.showerror("Error de Formato", "La cantidad ingresada no es un número entero válido.", parent=self.root)
            return isbn, None

    def gui_abastecer_libro(self):
        """Maneja la lógica para abastecer un libro."""
        # Obtener libro seleccionado si hay
        selected_isbn = self.tree_catalogo.focus()
        libro_seleccionado = self.tienda.buscar_libro_por_isbn(selected_isbn) if selected_isbn else None

        isbn, cantidad = self._ask_isbn_and_cantidad(
            title="Abastecer Libro",
            prompt_libro="ISBN del libro a abastecer:",
            prompt_cantidad="Cantidad a abastecer:",
            libro_info=libro_seleccionado
        )
        if isbn and cantidad:
            exito, msg = self.tienda.abastecer_libro(isbn, cantidad)
            messagebox.showinfo("Resultado de Abastecimiento", msg)
            if exito:
                self.actualizar_estado_caja_label()
                self.gui_mostrar_catalogo_completo() # Refrescar

    def gui_vender_libro(self):
        """Maneja la lógica para vender un libro."""
        selected_isbn = self.tree_catalogo.focus()
        libro_seleccionado = self.tienda.buscar_libro_por_isbn(selected_isbn) if selected_isbn else None

        isbn, cantidad = self._ask_isbn_and_cantidad(
            title="Vender Libro",
            prompt_libro="ISBN del libro a vender:",
            prompt_cantidad="Cantidad a vender (Stock, PV):", # Info extra se añade en _ask...
            libro_info=libro_seleccionado
        )
        if isbn and cantidad:
            exito, msg = self.tienda.vender_libro(isbn, cantidad)
            messagebox.showinfo("Resultado de Venta", msg)
            if exito:
                self.actualizar_estado_caja_label()
                self.gui_mostrar_catalogo_completo() # Refrescar

    def gui_buscar_por_isbn(self):
        """Busca un libro por ISBN y lo muestra."""
        isbn = simpledialog.askstring("Buscar por ISBN", "Ingrese el ISBN a buscar:", parent=self.root)
        if isbn:
            libro = self.tienda.buscar_libro_por_isbn(isbn)
            if libro:
                self.poblar_treeview_catalogo([libro]) # Mostrar solo este libro
                # Seleccionar el libro en el treeview y mostrar portada
                if self.tree_catalogo.exists(isbn):
                    self.tree_catalogo.selection_set(isbn)
                    self.tree_catalogo.focus(isbn)
                    self.gui_mostrar_portada_libro_api(isbn)
                self.gui_ver_detalle_libro_popup(isbn) # Mostrar detalles en popup
            else:
                self.limpiar_treeview_catalogo() # Limpiar si no se encontró
                messagebox.showinfo("Búsqueda sin Éxito", f"No se encontró ningún libro con el ISBN '{isbn}'.")
                self.cover_image_display_label.config(text="Libro no encontrado.", image=None)
                self.current_cover_photo = None

    def gui_buscar_por_titulo(self):
        """Busca libros por título (parcial) y los muestra."""
        titulo_parcial = simpledialog.askstring("Buscar por Título", "Ingrese parte del título a buscar:", parent=self.root)
        if titulo_parcial:
            libros_encontrados = self.tienda.buscar_libros_por_titulo(titulo_parcial)
            self.poblar_treeview_catalogo(libros_encontrados)
            if not libros_encontrados:
                messagebox.showinfo("Búsqueda sin Éxito", f"No se encontraron libros cuyo título contenga '{titulo_parcial}'.")
                self.cover_image_display_label.config(text="Sin resultados.", image=None)
                self.current_cover_photo = None
            elif len(libros_encontrados) == 1: # Si solo hay un resultado, mostrar su portada
                self.gui_mostrar_portada_libro_api(libros_encontrados[0].isbn)


    def gui_mostrar_libro_especial(self, tipo_busqueda: str):
        """Muestra el libro más costoso, menos costoso o más vendido."""
        libro_encontrado = None
        titulo_ventana_popup = "Resultado de Búsqueda Especial"
        mensaje_info = ""

        if tipo_busqueda == "costoso":
            libro_encontrado = self.tienda.buscar_libro_mas_costoso()
            titulo_ventana_popup = "Libro Más Costoso"
            mensaje_info = "Este es el libro con el precio de venta más alto en el catálogo."
        elif tipo_busqueda == "barato":
            libro_encontrado = self.tienda.buscar_libro_menos_costoso()
            titulo_ventana_popup = "Libro Menos Costoso"
            mensaje_info = "Este es el libro con el precio de venta más bajo en el catálogo."
        elif tipo_busqueda == "mas_vendido":
            libro_encontrado = self.tienda.buscar_libro_mas_vendido()
            titulo_ventana_popup = "Libro Más Vendido"
            if libro_encontrado:
                mensaje_info = f"Este es el libro más vendido, con {libro_encontrado.total_vendido_consulta} unidades vendidas."
            else:
                mensaje_info = "No se han registrado ventas o no hay datos suficientes."


        if libro_encontrado:
            self.poblar_treeview_catalogo([libro_encontrado]) # Mostrar solo este libro
            # Seleccionar el libro y mostrar portada
            if self.tree_catalogo.exists(libro_encontrado.isbn):
                 self.tree_catalogo.selection_set(libro_encontrado.isbn)
                 self.tree_catalogo.focus(libro_encontrado.isbn)
                 self.gui_mostrar_portada_libro_api(libro_encontrado.isbn)
            messagebox.showinfo(titulo_ventana_popup, f"{mensaje_info}\n\n{str(libro_encontrado)}", parent=self.root)
        else:
            self.limpiar_treeview_catalogo() # Limpiar si no se encontró
            messagebox.showinfo(titulo_ventana_popup, f"No se pudo determinar el libro para '{tipo_busqueda}' (catálogo vacío o sin datos relevantes).")
            self.cover_image_display_label.config(text="Sin resultados.", image=None)
            self.current_cover_photo = None

    def gui_transacciones_abastecimiento_libro(self):
        """Muestra la cantidad de transacciones de abastecimiento para un libro."""
        selected_isbn = self.tree_catalogo.focus()
        initial_val = selected_isbn if selected_isbn else ""
        isbn = simpledialog.askstring("Transacciones de Abastecimiento", "Ingrese el ISBN del libro:", initialvalue=initial_val, parent=self.root)
        if isbn:
            exito, resultado = self.tienda.calcular_transacciones_abastecimiento(isbn)
            if exito:
                messagebox.showinfo("Resultado", f"El libro con ISBN '{isbn}' tiene {resultado} transacciones de abastecimiento registradas.")
            else: # resultado contiene el mensaje de error
                messagebox.showerror("Error", resultado)

    def gui_ver_detalle_libro_popup(self, isbn: str):
        """Muestra una ventana emergente con detalles y transacciones de un libro."""
        libro = self.tienda.buscar_libro_por_isbn(isbn)
        if not libro:
            messagebox.showerror("Error", f"No se pudo encontrar el libro con ISBN {isbn} para mostrar detalles.")
            return

        transacciones_libro = self.tienda.obtener_transacciones_de_libro(isbn)

        # Crear ventana emergente (Toplevel)
        detail_popup_window = tk.Toplevel(self.root)
        detail_popup_window.title(f"Detalles del Libro: {libro.titulo[:40]}...") # Acortar título si es largo
        detail_popup_window.geometry("650x500") # Tamaño de la ventana de detalles
        detail_popup_window.transient(self.root) # Hacerla modal
        detail_popup_window.grab_set() # Capturar foco

        # Frame para la información del libro
        info_libro_frame = ttk.LabelFrame(detail_popup_window, text="Información del Libro", padding="10")
        info_libro_frame.pack(padx=10, pady=10, fill=tk.X)
        info_texto = (
            f"ISBN: {libro.isbn}\n"
            f"Título: {libro.titulo}\n"
            f"Precio Compra: ${libro.precio_compra:,.2f}\n"
            f"Precio Venta: ${libro.precio_venta:,.2f}\n"
            f"Cantidad Actual en Stock: {libro.cantidad_actual}"
        )
        ttk.Label(info_libro_frame, text=info_texto, justify=tk.LEFT, font=("Arial", 10)).pack(anchor=tk.NW)

        # Frame para las transacciones
        transacciones_frame = ttk.LabelFrame(detail_popup_window, text="Historial de Transacciones", padding="10")
        transacciones_frame.pack(padx=10, pady=(0,10), fill=tk.BOTH, expand=True)

        trans_tree = ttk.Treeview(transacciones_frame, columns=("ID", "Tipo", "Fecha", "Cantidad"), show="headings")
        trans_tree.heading("ID", text="ID"); trans_tree.column("ID", width=60, anchor=tk.E)
        trans_tree.heading("Tipo", text="Tipo"); trans_tree.column("Tipo", width=120)
        trans_tree.heading("Fecha", text="Fecha y Hora"); trans_tree.column("Fecha", width=180)
        trans_tree.heading("Cantidad", text="Cant."); trans_tree.column("Cantidad", width=80, anchor=tk.E)

        for t in transacciones_libro:
            trans_tree.insert("", tk.END, values=(t.id, t.tipo.capitalize(), t.fecha.strftime('%Y-%m-%d %H:%M:%S'), t.cantidad))
        
        trans_scrollbar = ttk.Scrollbar(transacciones_frame, orient=tk.VERTICAL, command=trans_tree.yview)
        trans_tree.configure(yscrollcommand=trans_scrollbar.set)
        trans_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        trans_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        if not transacciones_libro:
             ttk.Label(transacciones_frame, text="No hay transacciones registradas para este libro.").pack(pady=10)

        ttk.Button(detail_popup_window, text="Cerrar Detalles", command=detail_popup_window.destroy).pack(pady=10, ipady=4)
        detail_popup_window.wait_window() # Esperar a que se cierre esta ventana


    def on_closing_main_window(self):
        """Manejador para el evento de cierre de la ventana principal."""
        if messagebox.askokcancel("Salir", "¿Está seguro de que desea salir de la aplicación?"):
            if hasattr(self, 'db_manager') and self.db_manager: # Asegurarse de que db_manager exista
                self.db_manager.close() # Cerrar la conexión a la BD
            self.root.destroy() # Destruir la ventana principal

# --- Sección 6: Punto de Entrada Principal de la Aplicación ---
if __name__ == "__main__":
    root = tk.Tk() # Crear la ventana raíz de Tkinter
    
    # Intentar crear la instancia de la aplicación.
    # El constructor de TiendaLibrosApp maneja errores críticos de conexión/inicialización.
    app_instance = TiendaLibrosApp(root)

    # Si la aplicación no se inicializó correctamente (ej. db_manager es None o tienda no se creó),
    # root.destroy() ya se llamó en el constructor de TiendaLibrosApp,
    # por lo que no es necesario ejecutar mainloop.
    if hasattr(app_instance, 'db_manager') and app_instance.db_manager and \
       hasattr(app_instance, 'tienda') and app_instance.tienda:
        root.protocol("WM_DELETE_WINDOW", app_instance.on_closing_main_window) # Manejar cierre con el botón X
        root.mainloop() # Iniciar el bucle principal de eventos de Tkinter
    else:
        print("La aplicación no pudo inicializarse correctamente y se cerrará.")
        # Si root no fue destruida, destruirla ahora.
        if root.winfo_exists():
            root.destroy()