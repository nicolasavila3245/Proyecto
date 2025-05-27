-- ===================================================================================
-- Script para configurar la Base de Datos TiendaLibrosDB en SQL Server
-- Servidor: Lorena\SQLEXPRESSV2
-- Autenticaci�n: SQL Server (Usuario: SA, Contrase�a: tu_contrase�a)
-- ===================================================================================

-- PASO 1: Con�ctese a su instancia de SQL Server (Lorena\SQLEXPRESSV2) usando SSMS.
-- PASO 2: Ejecute este script.

-- --- Secci�n 1: Creaci�n y Selecci�n de la Base de Datos ---
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'TiendaLibrosDB')
BEGIN
    CREATE DATABASE TiendaLibrosDB;
    PRINT 'Base de datos TiendaLibrosDB creada.';
END
ELSE
    PRINT 'Base de datos TiendaLibrosDB ya existe.';
GO

USE TiendaLibrosDB; -- Asegurarse de que todas las operaciones siguientes se realicen en esta BD
GO

-- --- Secci�n 2: Eliminaci�n de Tablas Existentes (para re-ejecuci�n limpia) ---
-- Eliminar en orden inverso de dependencia debido a las Foreign Keys
IF OBJECT_ID('dbo.Transacciones', 'U') IS NOT NULL
    DROP TABLE dbo.Transacciones;
    PRINT 'Tabla Transacciones eliminada (si exist�a).';
GO

IF OBJECT_ID('dbo.ConfiguracionTienda', 'U') IS NOT NULL
    DROP TABLE dbo.ConfiguracionTienda;
    PRINT 'Tabla ConfiguracionTienda eliminada (si exist�a).';
GO

IF OBJECT_ID('dbo.Libros', 'U') IS NOT NULL
    DROP TABLE dbo.Libros;
    PRINT 'Tabla Libros eliminada (si exist�a).';
GO

-- --- Secci�n 3: Creaci�n de Tablas ---

-- Tabla Libros: Almacena la informaci�n de cada libro en el cat�logo.
CREATE TABLE Libros (
    ISBN VARCHAR(20) PRIMARY KEY NOT NULL,      -- Identificador �nico del libro (International Standard Book Number)
    Titulo NVARCHAR(255) NOT NULL,             -- T�tulo del libro (NVARCHAR para soportar caracteres internacionales)
    PrecioCompra DECIMAL(10, 2) NOT NULL,       -- Costo de adquisici�n del libro para la tienda
    PrecioVenta DECIMAL(10, 2) NOT NULL,        -- Precio al que se vende el libro al cliente
    CantidadActual INT NOT NULL DEFAULT 0       -- Stock actual del libro en la tienda
);
PRINT 'Tabla Libros creada.';
GO

-- Tabla Transacciones: Registra todas las ventas y abastecimientos de libros.
CREATE TABLE Transacciones (
    ID INT PRIMARY KEY IDENTITY(1,1),       -- Identificador �nico autoincremental para cada transacci�n
    LibroISBN VARCHAR(20) NOT NULL,         -- ISBN del libro involucrado en la transacci�n (Foreign Key a Libros.ISBN)
    TipoTransaccion VARCHAR(15) NOT NULL    -- Tipo de transacci�n: 'venta' o 'abastecimiento'
        CHECK (TipoTransaccion IN ('venta', 'abastecimiento')), -- Restricci�n para asegurar valores v�lidos
    FechaTransaccion DATETIME NOT NULL DEFAULT GETDATE(), -- Fecha y hora en que se realiz� la transacci�n (valor por defecto: actual)
    Cantidad INT NOT NULL,                  -- N�mero de ejemplares movidos en la transacci�n
    CONSTRAINT FK_Transacciones_Libro FOREIGN KEY (LibroISBN) REFERENCES Libros(ISBN)
        ON DELETE CASCADE -- Si se elimina un libro, se eliminan autom�ticamente sus transacciones asociadas.
);
PRINT 'Tabla Transacciones creada.';
GO

-- Tabla ConfiguracionTienda: Almacena configuraciones globales de la tienda, como el saldo de la caja.
CREATE TABLE ConfiguracionTienda (
    Clave VARCHAR(50) PRIMARY KEY NOT NULL, -- Nombre de la configuraci�n (ej. 'Caja')
    Valor DECIMAL(18, 2) NOT NULL           -- Valor de la configuraci�n
);
PRINT 'Tabla ConfiguracionTienda creada.';
GO

-- --- Secci�n 4: Inserci�n de Datos Iniciales y de Ejemplo ---

-- Insertar valor inicial para la Caja en ConfiguracionTienda
-- Se hace condicional para no duplicar si el script se ejecuta varias veces.
IF NOT EXISTS (SELECT 1 FROM ConfiguracionTienda WHERE Clave = 'Caja')
BEGIN
    INSERT INTO ConfiguracionTienda (Clave, Valor) VALUES ('Caja', 1000000.00); -- Inversi�n inicial de la tienda
    PRINT 'Valor inicial para Caja (1,000,000.00) insertado en ConfiguracionTienda.';
END
ELSE
    PRINT 'Valor para Caja ya existe en ConfiguracionTienda.';
GO

-- Insertar Libros de Ejemplo
-- Se hace condicional para no duplicar. CantidadActual se pone a 0, luego se actualiza con abastecimientos.
PRINT 'Insertando libros de ejemplo...';
INSERT INTO Libros (ISBN, Titulo, PrecioCompra, PrecioVenta, CantidadActual)
SELECT '978-0321765723', N'Cien A�os de Soledad', 20.00, 35.50, 0 WHERE NOT EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-0321765723')
UNION ALL
SELECT '978-8437604947', N'El Amor en los Tiempos del C�lera', 18.50, 30.00, 0 WHERE NOT EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-8437604947')
UNION ALL
SELECT '978-1984801903', N'La Sombra del Viento', 22.75, 40.25, 0 WHERE NOT EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-1984801903')
UNION ALL
SELECT '978-0743273565', N'El Gran Gatsby', 15.00, 25.00, 0 WHERE NOT EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-0743273565');
PRINT 'Libros de ejemplo insertados (si no exist�an).';
GO

-- Insertar Transacciones de Ejemplo (Abastecimientos y Ventas)
-- Estas simulan operaciones iniciales. El saldo de la caja en BD NO se actualiza aqu�,
-- ya que la l�gica de la app Python maneja la caja al realizar operaciones.
-- Estas transacciones ayudan a tener datos para probar las consultas.
PRINT 'Insertando transacciones de ejemplo...';

-- Abastecer "Cien A�os de Soledad"
IF EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-0321765723' AND CantidadActual = 0)
BEGIN
    UPDATE Libros SET CantidadActual = 10 WHERE ISBN = '978-0321765723';
    INSERT INTO Transacciones (LibroISBN, TipoTransaccion, Cantidad, FechaTransaccion)
    SELECT '978-0321765723', 'abastecimiento', 10, DATEADD(day, -5, GETDATE()) -- Fecha hace 5 d�as
    WHERE NOT EXISTS (SELECT 1 FROM Transacciones WHERE LibroISBN = '978-0321765723' AND Cantidad = 10 AND TipoTransaccion = 'abastecimiento' AND DATEDIFF(day, FechaTransaccion, DATEADD(day, -5, GETDATE())) = 0);
    PRINT 'Abastecimiento inicial para "Cien A�os de Soledad" realizado.';
END
GO

-- Abastecer "El Amor en los Tiempos del C�lera"
IF EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-8437604947' AND CantidadActual = 0)
BEGIN
    UPDATE Libros SET CantidadActual = 5 WHERE ISBN = '978-8437604947';
    INSERT INTO Transacciones (LibroISBN, TipoTransaccion, Cantidad, FechaTransaccion)
    SELECT '978-8437604947', 'abastecimiento', 5, DATEADD(day, -4, GETDATE()) -- Fecha hace 4 d�as
    WHERE NOT EXISTS (SELECT 1 FROM Transacciones WHERE LibroISBN = '978-8437604947' AND Cantidad = 5 AND TipoTransaccion = 'abastecimiento' AND DATEDIFF(day, FechaTransaccion, DATEADD(day, -4, GETDATE())) = 0);
    PRINT 'Abastecimiento inicial para "El Amor en los Tiempos del C�lera" realizado.';
END
GO

-- Simular una venta de "Cien A�os de Soledad"
IF EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-0321765723' AND CantidadActual >= 2) AND
   NOT EXISTS (SELECT 1 FROM Transacciones WHERE LibroISBN = '978-0321765723' AND TipoTransaccion = 'venta' AND Cantidad = 2 AND DATEDIFF(day, FechaTransaccion, DATEADD(day, -2, GETDATE())) = 0)
BEGIN
    UPDATE Libros SET CantidadActual = CantidadActual - 2 WHERE ISBN = '978-0321765723';
    INSERT INTO Transacciones (LibroISBN, TipoTransaccion, Cantidad, FechaTransaccion) VALUES
    ('978-0321765723', 'venta', 2, DATEADD(day, -2, GETDATE())); -- Fecha hace 2 d�as
    PRINT 'Venta simulada de "Cien A�os de Soledad" realizada.';
END
GO

-- Simular un segundo abastecimiento para "Cien A�os de Soledad"
IF EXISTS (SELECT 1 FROM Libros WHERE ISBN = '978-0321765723') AND
   NOT EXISTS (SELECT 1 FROM Transacciones WHERE LibroISBN = '978-0321765723' AND TipoTransaccion = 'abastecimiento' AND Cantidad = 3 AND DATEDIFF(day, FechaTransaccion, DATEADD(day, -1, GETDATE())) = 0)
BEGIN
    UPDATE Libros SET CantidadActual = CantidadActual + 3 WHERE ISBN = '978-0321765723';
    INSERT INTO Transacciones (LibroISBN, TipoTransaccion, Cantidad, FechaTransaccion) VALUES
    ('978-0321765723', 'abastecimiento', 3, DATEADD(day, -1, GETDATE())); -- Fecha hace 1 d�a
    PRINT 'Segundo abastecimiento simulado de "Cien A�os de Soledad" realizado.';
END
GO
PRINT 'Transacciones de ejemplo insertadas (si no exist�an y las condiciones se cumpl�an).';

-- --- Secci�n 5: Verificaci�n de Datos (Opcional) ---
PRINT '--- Verificaci�n de Datos ---';
SELECT 'Tabla Libros:' AS Tabla, * FROM Libros ORDER BY Titulo;
SELECT 'Tabla Transacciones:' AS Tabla, * FROM Transacciones ORDER BY FechaTransaccion;
SELECT 'Tabla ConfiguracionTienda:' AS Tabla, * FROM ConfiguracionTienda;
GO

PRINT '--- Script de configuraci�n de base de datos completado. ---';
GO