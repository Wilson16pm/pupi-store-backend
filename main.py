from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime
import models
from database import engine, SessionLocal, get_db, get_current_user
from auth import verificar_contrasena, crear_token_acceso, obtener_hash_contrasena

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pupi Store API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# --- ESQUEMAS ---
class ProductoSchema(BaseModel):
    categoria: str
    marca: str
    modelo: str
    imei_serial: str = ""
    stock: int
    precio_compra: float
    precio_venta: float
    proveedor: str = ""
    color: str = ""

class ClienteSchema(BaseModel):
    nombre_completo: str
    dni: str
    direccion: str = ""
    distrito: str = ""
    correo: str = ""
    telefono: str = ""

class VentaSchema(BaseModel):
    id_cliente: int
    id_producto: int
    precio_equipo: float
    cuota_inicial: float
    no_cuotas: int
    cuota_mensual: float
    tipo_venta: str

class EditarCuotaSchema(BaseModel):
    monto: float
    fecha_vencimiento: str

class UsuarioSchema(BaseModel):
    nombres: str
    apellidos: str
    usuario: str
    contrasena: str
    dni: str
    celular: str
    rol: str

# --- RUTA BASE ---
@app.get("/")
def inicio():
    return {"mensaje": "Servidor funcionando"}

# --- LOGIN CON JWT Y MIGRACIÓN AUTOMÁTICA ---
@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.Usuario == form_data.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    # 1. Intentar verificar si es un hash (seguridad normal)
    password_correcta = False
    try:
        password_correcta = verificar_contrasena(form_data.password, user.Contrasena)
    except Exception:
        pass # Si falla, es porque la contraseña en BD es texto plano (migración vieja)

    # 2. MIGRACIÓN AUTOMÁTICA: Si es texto plano y coincide, lo encriptamos y guardamos
    if not password_correcta and user.Contrasena == form_data.password:
        user.Contrasena = obtener_hash_contrasena(form_data.password)
        db.commit()
        password_correcta = True

    if not password_correcta:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    
    token_acceso = crear_token_acceso(data={"sub": user.Usuario})
    
    return {
        "access_token": token_acceso, 
        "token_type": "bearer",
        "mensaje": "Login exitoso",
        "id": user.ID,
        "usuario": user.Usuario,
        "nombre_completo": f"{user.Nombres} {user.Apellidos}",
        "rol": user.Rol
    }

# --- DASHBOARD ---
@app.get("/api/dashboard/{id_usuario}", dependencies=[Depends(get_current_user)])
def obtener_dashboard(id_usuario: int, db: Session = Depends(get_db)):
    ventas_totales = db.query(func.sum(models.Venta.Precio_Equipo)).scalar() or 0
    ganancia_total = db.query(
        func.sum(models.Venta.Precio_Equipo - models.Inventario.Precio_Compra)
    ).join(models.Inventario, models.Venta.ID_Producto == models.Inventario.ID_Producto).scalar() or 0
    productos_stock = db.query(func.sum(models.Inventario.Stock_Actual)).scalar() or 0
    cuotas_cobradas = db.query(models.Cuota).filter(models.Cuota.Estado == "PAGADO").count()
    cuotas_pendientes = db.query(models.Cuota).filter(models.Cuota.Estado == "PENDIENTE").count()
    
    categorias = db.query(
        models.Inventario.Categoria, 
        func.count(models.Venta.ID_Venta)
    ).join(models.Venta, models.Venta.ID_Producto == models.Inventario.ID_Producto).group_by(models.Inventario.Categoria).all()
    ventas_por_categoria = {cat: count for cat, count in categorias}
    
    top_productos = db.query(
        models.Inventario.Marca,
        models.Inventario.Modelo,
        func.count(models.Venta.ID_Venta).label('total')
    ).join(models.Venta, models.Venta.ID_Producto == models.Inventario.ID_Producto).group_by(
        models.Inventario.Marca, models.Inventario.Modelo
    ).order_by(func.count(models.Venta.ID_Venta).desc()).limit(4).all()
    top_prods = [{"nombre": f"{marca} {modelo}", "cantidad": total} for marca, modelo, total in top_productos]

    return {
        "ventas_totales": float(ventas_totales),
        "ganancia_total": float(ganancia_total),
        "productos_stock": int(productos_stock),
        "cuotas_cobradas": cuotas_cobradas,
        "cuotas_pendientes": cuotas_pendientes,
        "ventas_por_categoria": ventas_por_categoria,
        "top_productos": top_prods
    }

# --- INVENTARIO (PROTEGIDO) ---
@app.get("/api/inventario", dependencies=[Depends(get_current_user)])
def listar_inventario(db: Session = Depends(get_db)):
    return db.query(models.Inventario).all()

@app.get("/api/inventario/disponibles", dependencies=[Depends(get_current_user)])
def listar_disponibles(db: Session = Depends(get_db)):
    return db.query(models.Inventario).filter(models.Inventario.Estado == "Disponible", models.Inventario.Stock_Actual > 0).all()

@app.post("/api/inventario", dependencies=[Depends(get_current_user)])
def crear_producto(prod: ProductoSchema, db: Session = Depends(get_db)):
    if prod.categoria in ["Celular", "Laptop"]:
        if not prod.imei_serial or prod.imei_serial.strip() == "":
            raise HTTPException(status_code=400, detail="El IMEI es obligatorio")
        if db.query(models.Inventario).filter(models.Inventario.IMEI_Serial == prod.imei_serial).first():
            raise HTTPException(status_code=400, detail="Este IMEI ya está registrado")
        prod.stock = 1
    else:
        prod.imei_serial = "N/A"

    nuevo_producto = models.Inventario(
        Categoria=prod.categoria, Marca=prod.marca.upper(), Modelo=prod.modelo.upper(),
        IMEI_Serial=prod.imei_serial, Stock_Inicial=prod.stock, Stock_Actual=prod.stock,
        Precio_Compra=prod.precio_compra, Precio_Venta=prod.precio_venta,
        Proveedor=prod.proveedor.upper(), Fecha_Ingreso=datetime.now().date(),
        Color=prod.color.upper(), Estado="Disponible"
    )
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)
    return {"mensaje": "Producto registrado", "id": nuevo_producto.ID_Producto}

@app.put("/api/inventario/{id_producto}", dependencies=[Depends(get_current_user)])
def actualizar_producto(id_producto: int, prod: ProductoSchema, db: Session = Depends(get_db)):
    producto_db = db.query(models.Inventario).filter(models.Inventario.ID_Producto == id_producto).first()
    if not producto_db:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    producto_db.Categoria = prod.categoria
    producto_db.Marca = prod.marca.upper()
    producto_db.Modelo = prod.modelo.upper()
    producto_db.Stock_Actual = prod.stock
    producto_db.Precio_Compra = prod.precio_compra
    producto_db.Precio_Venta = prod.precio_venta
    producto_db.Proveedor = prod.proveedor.upper()
    producto_db.Color = prod.color.upper()
    db.commit()
    return {"mensaje": "Producto actualizado"}

@app.delete("/api/inventario/{id_producto}", dependencies=[Depends(get_current_user)])
def eliminar_producto(id_producto: int, db: Session = Depends(get_db)):
    producto_db = db.query(models.Inventario).filter(models.Inventario.ID_Producto == id_producto).first()
    if not producto_db:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    db.delete(producto_db)
    db.commit()
    return {"mensaje": "Producto eliminado"}

# --- CLIENTES (PROTEGIDO) ---
@app.get("/api/clientes", dependencies=[Depends(get_current_user)])
def listar_clientes(db: Session = Depends(get_db)):
    return db.query(models.Cliente).all()

@app.post("/api/clientes", dependencies=[Depends(get_current_user)])
def crear_cliente(cliente: ClienteSchema, db: Session = Depends(get_db)):
    existe = db.query(models.Cliente).filter(models.Cliente.DNI == cliente.dni).first()
    if existe:
        raise HTTPException(status_code=400, detail="El DNI ya está registrado")
    nuevo_cliente = models.Cliente(
        Nombre_Completo=cliente.nombre_completo.upper(),
        DNI=cliente.dni, Direccion=cliente.direccion.upper(),
        Distrito=cliente.distrito.upper(), Correo=cliente.correo, Telefono=cliente.telefono
    )
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    return {"mensaje": "Cliente registrado", "id": nuevo_cliente.ID_Cliente}

# --- VENTAS (PROTEGIDO) ---
@app.get("/api/ventas", dependencies=[Depends(get_current_user)])
def listar_ventas(db: Session = Depends(get_db)):
    ventas = db.query(
        models.Venta, models.Cliente.Nombre_Completo, models.Cliente.Telefono, models.Inventario.Marca, models.Inventario.Modelo
    ).join(models.Cliente, models.Venta.ID_Cliente == models.Cliente.ID_Cliente
    ).join(models.Inventario, models.Venta.ID_Producto == models.Inventario.ID_Producto).all()
    
    resultado = []
    for v, nombre_cliente, telefono, marca, modelo in ventas:
        resultado.append({
            "ID_Venta": v.ID_Venta,
            "Fecha": v.Fecha_Venta,
            "Cliente": nombre_cliente,
            "Telefono": telefono,
            "Equipo": f"{marca} {modelo}",
            "Total": float(v.Precio_Equipo),
            "Tipo": v.Tipo_Venta,
            "Estado": v.Estado,
            "ID_Producto": v.ID_Producto 
        })
    return resultado

@app.post("/api/ventas", dependencies=[Depends(get_current_user)])
def registrar_venta(venta: VentaSchema, db: Session = Depends(get_db)):
    producto = db.query(models.Inventario).filter(models.Inventario.ID_Producto == venta.id_producto).first()
    if not producto or producto.Stock_Actual < 1 or producto.Estado == "Vendido":
        raise HTTPException(status_code=400, detail="El producto no está disponible")

    saldo_diferido = venta.precio_equipo - venta.cuota_inicial
    nueva_venta = models.Venta(
        Fecha_Venta=datetime.now().date(), ID_Cliente=venta.id_cliente, ID_Usuario=1,
        ID_Producto=venta.id_producto, Precio_Equipo=venta.precio_equipo,
        Cuota_Inicial=venta.cuota_inicial, Saldo_Diferido=saldo_diferido,
        No_Cuotas=venta.no_cuotas, Cuota_Mensual=venta.cuota_mensual,
        Tipo_Venta=venta.tipo_venta, Estado="ACTIVO" if venta.tipo_venta == "CRÉDITO" else "PAGADO"
    )
    db.add(nueva_venta)
    db.commit()
    db.refresh(nueva_venta)

    if venta.tipo_venta == "CRÉDITO" and venta.no_cuotas > 0:
        for i in range(1, venta.no_cuotas + 1):
            fecha_v = datetime.now()
            mes = fecha_v.month + i
            año = fecha_v.year + (mes - 1) // 12
            mes = (mes - 1) % 12 + 1
            fecha_vencimiento = fecha_v.replace(year=año, month=mes)
            nueva_cuota = models.Cuota(
                ID_Venta=nueva_venta.ID_Venta, Nro_Cuota=i, Monto=venta.cuota_mensual,
                Fecha_Vencimiento=fecha_vencimiento.date(), Estado="PENDIENTE"
            )
            db.add(nueva_cuota)

    producto.Stock_Actual -= 1
    if producto.Stock_Actual == 0: producto.Estado = "Vendido"
    db.commit()
    return {"mensaje": "Venta registrada", "id_venta": nueva_venta.ID_Venta}

@app.delete("/api/ventas/{id_venta}", dependencies=[Depends(get_current_user)])
def eliminar_venta(id_venta: int, db: Session = Depends(get_db)):
    venta = db.query(models.Venta).filter(models.Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    producto = db.query(models.Inventario).filter(models.Inventario.ID_Producto == venta.ID_Producto).first()
    if producto:
        producto.Stock_Actual += 1
        producto.Estado = "Disponible"
    db.query(models.Cuota).filter(models.Cuota.ID_Venta == id_venta).delete()
    db.delete(venta)
    db.commit()
    return {"mensaje": "Venta eliminada y stock restaurado"}

# --- CUOTAS Y COBRANZAS (PROTEGIDO) ---
@app.get("/api/cuotas/{id_venta}", dependencies=[Depends(get_current_user)])
def listar_cuotas(id_venta: int, db: Session = Depends(get_db)):
    return db.query(models.Cuota).filter(models.Cuota.ID_Venta == id_venta).order_by(models.Cuota.Nro_Cuota).all()

@app.put("/api/cuotas/{id_cuota}/pagar", dependencies=[Depends(get_current_user)])
def pagar_cuota(id_cuota: int, db: Session = Depends(get_db)):
    cuota = db.query(models.Cuota).filter(models.Cuota.ID_Cuota == id_cuota).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    if cuota.Estado == "PAGADO":
        raise HTTPException(status_code=400, detail="Esta cuota ya está pagada")
    cuota.Estado = "PAGADO"
    cuota.Fecha_Pago = datetime.now().date()
    cuotas_venta = db.query(models.Cuota).filter(models.Cuota.ID_Venta == cuota.ID_Venta).all()
    if all(c.Estado == "PAGADO" for c in cuotas_venta):
        venta = db.query(models.Venta).filter(models.Venta.ID_Venta == cuota.ID_Venta).first()
        venta.Estado = "PAGADO"
    db.commit()
    return {"mensaje": "Cuota pagada correctamente"}

@app.put("/api/cuotas/{id_cuota}/editar", dependencies=[Depends(get_current_user)])
def editar_cuota(id_cuota: int, datos: EditarCuotaSchema, db: Session = Depends(get_db)):
    cuota = db.query(models.Cuota).filter(models.Cuota.ID_Cuota == id_cuota).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    cuota.Monto = datos.monto
    try:
        cuota.Fecha_Vencimiento = datetime.strptime(datos.fecha_vencimiento, "%Y-%m-%d").date()
    except:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido")
    db.commit()
    return {"mensaje": "Cuota actualizada"}

@app.get("/api/cobranzas", dependencies=[Depends(get_current_user)])
def obtener_cobranzas(db: Session = Depends(get_db)):
    resultados = db.query(
        models.Cuota, models.Venta, models.Cliente, models.Inventario
    ).join(
        models.Venta, models.Cuota.ID_Venta == models.Venta.ID_Venta
    ).join(
        models.Cliente, models.Venta.ID_Cliente == models.Cliente.ID_Cliente
    ).join(
        models.Inventario, models.Venta.ID_Producto == models.Inventario.ID_Producto
    ).filter(
        models.Cuota.Estado == "PENDIENTE"
    ).order_by(
        models.Cuota.Fecha_Vencimiento.asc()
    ).all()

    cobranzas = []
    hoy = datetime.now().date()

    for cuota, venta, cliente, producto in resultados:
        dias_diferencia = (cuota.Fecha_Vencimiento - hoy).days
        estado_alerta = "AL_DIA"
        if dias_diferencia < 0:
            estado_alerta = "VENCIDA"
        elif dias_diferencia <= 3:
            estado_alerta = "POR_VENCER"
        cobranzas.append({
            "ID_Cuota": cuota.ID_Cuota,
            "ID_Venta": venta.ID_Venta,
            "Nro_Cuota": cuota.Nro_Cuota,
            "Cliente": cliente.Nombre_Completo,
            "Telefono": cliente.Telefono,
            "Equipo": f"{producto.Marca} {producto.Modelo}",
            "Monto": float(cuota.Monto),
            "Fecha_Vencimiento": cuota.Fecha_Vencimiento,
            "Dias_Diferencia": dias_diferencia,
            "Estado_Alerta": estado_alerta
        })
    return cobranzas

# --- USUARIOS (PROTEGIDO Y ENCRIPTADO) ---
@app.get("/api/usuarios", dependencies=[Depends(get_current_user)])
def listar_usuarios(db: Session = Depends(get_db)):
    usuarios = db.query(models.Usuario).all()
    return [{"ID": u.ID, "Nombres": u.Nombres, "Apellidos": u.Apellidos, "Usuario": u.Usuario, "DNI": u.DNI, "Celular": u.Celular, "Rol": u.Rol} for u in usuarios]

@app.post("/api/usuarios", dependencies=[Depends(get_current_user)])
def crear_usuario(usr: UsuarioSchema, db: Session = Depends(get_db)):
    if db.query(models.Usuario).filter(models.Usuario.Usuario == usr.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
    if db.query(models.Usuario).filter(models.Usuario.DNI == usr.dni).first():
        raise HTTPException(status_code=400, detail="El DNI ya está registrado")
    nuevo_usuario = models.Usuario(
        Nombres=usr.nombres.upper(), Apellidos=usr.apellidos.upper(),
        Usuario=usr.usuario, 
        Contrasena=obtener_hash_contrasena(usr.contrasena),
        DNI=usr.dni, Celular=usr.celular, Rol=usr.rol.upper()
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return {"mensaje": "Usuario registrado", "id": nuevo_usuario.ID}

@app.put("/api/usuarios/{id_usuario}", dependencies=[Depends(get_current_user)])
def actualizar_usuario(id_usuario: int, usr: UsuarioSchema, db: Session = Depends(get_db)):
    usuario_db = db.query(models.Usuario).filter(models.Usuario.ID == id_usuario).first()
    if not usuario_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if db.query(models.Usuario).filter(models.Usuario.Usuario == usr.usuario, models.Usuario.ID != id_usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
    
    usuario_db.Nombres = usr.nombres.upper()
    usuario_db.Apellidos = usr.apellidos.upper()
    usuario_db.Usuario = usr.usuario
    if usr.contrasena: 
        usuario_db.Contrasena = obtener_hash_contrasena(usr.contrasena)
    usuario_db.DNI = usr.dni
    usuario_db.Celular = usr.celular
    usuario_db.Rol = usr.rol.upper()
    db.commit()
    return {"mensaje": "Usuario actualizado"}

@app.delete("/api/usuarios/{id_usuario}", dependencies=[Depends(get_current_user)])
def eliminar_usuario(id_usuario: int, db: Session = Depends(get_db)):
    usuario_db = db.query(models.Usuario).filter(models.Usuario.ID == id_usuario).first()
    if not usuario_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if id_usuario == 1: 
        raise HTTPException(status_code=400, detail="No se puede eliminar al administrador principal")
    db.delete(usuario_db)
    db.commit()
    return {"mensaje": "Usuario eliminado"}