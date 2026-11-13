from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey
from database import Base

class Usuario(Base):
    __tablename__ = "Usuarios"
    ID = Column(Integer, primary_key=True, index=True)
    Nombres = Column(String(100), nullable=False)
    Apellidos = Column(String(100), nullable=False)
    Usuario = Column(String(50), unique=True, nullable=False)
    Contrasena = Column(String(255), nullable=False)
    DNI = Column(String(8), unique=True, nullable=False)
    Celular = Column(String(15), nullable=False)
    Rol = Column(String(20), nullable=False)

class Cliente(Base):
    __tablename__ = "Clientes"
    ID_Cliente = Column(Integer, primary_key=True, index=True)
    Nombre_Completo = Column(String(150), nullable=False)
    DNI = Column(String(8), unique=True, nullable=False)
    Direccion = Column(String(200))
    Distrito = Column(String(100))
    Correo = Column(String(100))
    Telefono = Column(String(15))
    Ruta_Foto = Column(String(255))

class Inventario(Base):
    __tablename__ = "Inventario"
    ID_Producto = Column(Integer, primary_key=True, index=True)
    Categoria = Column(String(50), nullable=False)
    Marca = Column(String(50), nullable=False)
    Modelo = Column(String(100), nullable=False)
    IMEI_Serial = Column(String(50))
    Stock_Inicial = Column(Integer, nullable=False)
    Stock_Actual = Column(Integer, nullable=False)
    Precio_Compra = Column(Numeric(10, 2), nullable=False)
    Precio_Venta = Column(Numeric(10, 2), nullable=False)
    Proveedor = Column(String(100))
    Fecha_Ingreso = Column(Date, nullable=False)
    Color = Column(String(50))
    Estado = Column(String(20), nullable=False)
    Observaciones = Column(String(255))

class Venta(Base):
    __tablename__ = "Ventas"
    ID_Venta = Column(Integer, primary_key=True, index=True)
    Fecha_Venta = Column(Date, nullable=False)
    ID_Cliente = Column(Integer, ForeignKey("Clientes.ID_Cliente"), nullable=False)
    ID_Usuario = Column(Integer, ForeignKey("Usuarios.ID"), nullable=False)
    ID_Producto = Column(Integer, ForeignKey("Inventario.ID_Producto"), nullable=False)
    Precio_Equipo = Column(Numeric(10, 2), nullable=False)
    Cuota_Inicial = Column(Numeric(10, 2), nullable=False)
    Saldo_Diferido = Column(Numeric(10, 2), nullable=False)
    No_Cuotas = Column(Integer, nullable=False)
    Cuota_Mensual = Column(Numeric(10, 2), nullable=False)
    Tipo_Venta = Column(String(20), nullable=False)
    Estado = Column(String(20), nullable=False)

class Cuota(Base):
    __tablename__ = "Cuotas"
    ID_Cuota = Column(Integer, primary_key=True, index=True)
    ID_Venta = Column(Integer, ForeignKey("Ventas.ID_Venta", ondelete="CASCADE"), nullable=False)
    Nro_Cuota = Column(Integer, nullable=False)
    Monto = Column(Numeric(10, 2), nullable=False)
    Fecha_Vencimiento = Column(Date, nullable=False)
    Estado = Column(String(20), nullable=False)
    Fecha_Pago = Column(Date, nullable=True)
    Observaciones = Column(String(255))