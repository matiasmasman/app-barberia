import random
from datetime import datetime, date, time, timedelta
from fastapi import FastAPI, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from auth import verify_password, create_access_token, SECRET_KEY, ALGORITHM

from database import engine, Base, get_db
import models
import services

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestor de Turnos Peluquería (SaaS)")
templates = Jinja2Templates(directory="templates")

# --- NUEVO MOTOR DE AUTENTICACIÓN POR COOKIES ---
def obtener_usuario_actual(request: Request, db: Session = Depends(get_db)):
    # Buscamos la cookie segura
    token = request.cookies.get("access_token")
    if not token:
        # Si no hay token, lo pateamos a la pantalla de login
        raise HTTPException(status_code=303, headers={"Location": "/login"})
        
    try:
        token = token.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
    except JWTError:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
        
    user = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
        
    return user

# --- RUTAS DE LOGIN Y LOGOUT ---
@app.get("/login", response_class=HTMLResponse)
def vista_login(request: Request, error: int = 0):
    return templates.TemplateResponse(
        request=request,
        name="login.html", 
        context={"request": request, "error": error}
    )

@app.post("/login")
def procesar_login(
    username: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=1", status_code=303)
        
    # Generamos el token de sesión
    access_token = create_access_token(data={"sub": user.username})
    
    # Redirigimos al admin pero inyectando la cookie segura (HttpOnly = True mitigación XSS)
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True, 
        samesite="lax"
    )
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token") # Destruimos la sesión
    return response

# --- NUEVA LÓGICA DE INICIALIZACIÓN SaaS ---


# 1. Página principal de reserva (para clientes)
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    comercio = db.query(models.Comercio).first()
    
    # NUEVO: Traemos todos los profesionales activos de este comercio
    profesionales = db.query(models.Profesional).filter_by(comercio_id=comercio.id, activo=True).all()
    servicios = db.query(models.Servicio).filter_by(comercio_id=comercio.id).all()
    hoy = date.today().isoformat()

    # Como el cliente puede elegir "Cualquiera", la validación de días cerrados
    # la pasamos a manejar dinámicamente con la API, así que enviamos listas vacías por ahora.
    return templates.TemplateResponse(
        request=request,
        name="reservar.html",
        context={
            "request": request,
            "profesionales": profesionales, # Pasamos los barberos al HTML
            "servicios": servicios,
            "hoy": hoy,
            "dias_js": "[]", 
            "fechas_cerradas": "[]",
        },
    )

# 2. Endpoint API de disponibilidad
@app.get("/api/disponibilidad")
def ver_disponibilidad(fecha: str, servicio_id: int, profesional_id: str, db: Session = Depends(get_db)):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    servicio = db.query(models.Servicio).filter(models.Servicio.id == servicio_id).first()
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    comercio = db.query(models.Comercio).first()

    # LÓGICA DINÁMICA: "cualquiera" vs "barbero específico"
    if profesional_id == "cualquiera":
        slots = services.calcular_horarios_comercio(db, comercio.id, fecha_obj, servicio.duracion_min)
    else:
        slots = services.calcular_horarios_disponibles(db, int(profesional_id), fecha_obj, servicio.duracion_min)
        
    return {"disponibles": slots}

# 3. Procesar reserva de turno
@app.post("/reservar")
def procesar_reserva(
    cliente_nombre: str = Form(...),
    cliente_telefono: str = Form(...),
    servicio_id: int = Form(...),
    profesional_id: str = Form(...), # NUEVO: Recibimos este dato del formulario
    fecha: str = Form(...),
    hora: str = Form(...),
    db: Session = Depends(get_db),
):
    if not cliente_telefono.isdigit() or len(cliente_telefono) != 10:
        raise HTTPException(status_code=400, detail="Número inválido.")

    comercio = db.query(models.Comercio).first()
    servicio = db.query(models.Servicio).filter(models.Servicio.id == servicio_id).first()
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    
    profesional_asignado_id = None

    # LÓGICA DE AUTO-ASIGNACIÓN REPARTIDA
    if profesional_id == "cualquiera":
        profesionales = db.query(models.Profesional).filter_by(comercio_id=comercio.id, activo=True).all()
        
        # Mezclamos la lista de barberos al azar para equilibrar el trabajo
        random.shuffle(profesionales)
        
        for p in profesionales:
            slots = services.calcular_horarios_disponibles(db, p.id, fecha_obj, servicio.duracion_min)
            if hora in slots:
                profesional_asignado_id = p.id
                break
                
        if not profesional_asignado_id:
            raise HTTPException(status_code=400, detail="Ups, parece que alguien acaba de reservar ese horario.")
    else:
        # Eligió un barbero específico
        profesional_asignado_id = int(profesional_id)

    # El resto sigue igual, pero usando profesional_asignado_id
    inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    fin = inicio + timedelta(minutes=servicio.duracion_min)

    ocupados = services.obtener_turnos_ocupados(db, profesional_asignado_id, inicio.date())
    for t in ocupados:
        if inicio < t.fecha_hora_fin and fin > t.fecha_hora_inicio:
            raise HTTPException(status_code=400, detail="El horario acaba de ser ocupado. Elegí otro.")

    nuevo_turno = models.Turno(
        profesional_id=profesional_asignado_id,
        servicio_id=servicio.id,
        cliente_nombre=cliente_nombre,
        cliente_telefono=cliente_telefono,
        fecha_hora_inicio=inicio,
        fecha_hora_fin=fin,
        estado="confirmado",
    )
    db.add(nuevo_turno)
    db.commit()

    return RedirectResponse(url="/?reserva=exitosa", status_code=303)

# 4. Panel admin (Inicio)
@app.get("/admin", response_class=HTMLResponse)
def panel_admin(
    request: Request,
    fecha: str = None,
    profesional_id: int = 0,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual), 
):
    comercio = db.query(models.Comercio).first()
    profesionales = db.query(models.Profesional).filter_by(comercio_id=comercio.id, activo=True).all()
    
    if not profesionales:
        return HTMLResponse("No hay profesionales configurados.")

    # --- NUEVO: LÓGICA RBAC (Blue Team) ---
    # Si es un empleado, lo obligamos a ver solo su agenda, sin importar qué ponga en la URL
    if usuario_actual.rol == "profesional":
        profesional_id = usuario_actual.profesional_id
    # --------------------------------------

    def armar_semana(fecha_referencia):
        inicio_sem = fecha_referencia - timedelta(days=fecha_referencia.weekday())
        fin_sem = inicio_sem + timedelta(days=6)
        
        # Filtro: Todos vs Uno solo
        if profesional_id == 0:
            filtro_ids = [p.id for p in profesionales]
        else:
            filtro_ids = [profesional_id]
            
        turnos_sem = db.query(models.Turno).filter(
            models.Turno.profesional_id.in_(filtro_ids),
            models.Turno.fecha_hora_inicio >= datetime.combine(inicio_sem, time.min),
            models.Turno.fecha_hora_inicio <= datetime.combine(fin_sem, time.max),
            models.Turno.estado == "confirmado"
        ).order_by(models.Turno.fecha_hora_inicio.asc()).all()

        mapa_dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        semana_estructurada = []

        for i in range(7):
            dia_actual = inicio_sem + timedelta(days=i)

            if dia_actual < date.today():
                continue
                
            turnos_dia = [t for t in turnos_sem if t.fecha_hora_inicio.date() == dia_actual]
            
            semana_estructurada.append({
                "fecha_str": dia_actual.strftime("%d/%m"),
                "nombre_dia": mapa_dias[dia_actual.weekday()],
                "es_hoy": dia_actual == date.today(),
                "turnos": turnos_dia
            })
            
        return semana_estructurada, inicio_sem, fin_sem

    fecha_ref = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else date.today()
    semana_estructurada, inicio_semana, fin_semana = armar_semana(fecha_ref)

    if not semana_estructurada and not fecha:
        fecha_ref = fecha_ref + timedelta(days=(7 - fecha_ref.weekday()))
        semana_estructurada, inicio_semana, fin_semana = armar_semana(fecha_ref)

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request, 
            "semana": semana_estructurada, 
            "fecha": fecha_ref.isoformat(),
            "inicio_str": inicio_semana.strftime("%d/%m"),
            "fin_str": fin_semana.strftime("%d/%m"),
            "hoy_esta_en_semana": inicio_semana <= date.today() <= fin_semana,
            "profesionales": profesionales,
            "prof_actual_id": profesional_id,
            "usuario": usuario_actual # NUEVO: Le pasamos el usuario al HTML
        },
    )

# --- 5. RUTAS DE HORARIO HABITUAL ---
@app.get("/admin/config/horarios", response_class=HTMLResponse)
def panel_horarios(request: Request, db: Session = Depends(get_db), usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    profesional = db.query(models.Profesional).first()
    horarios = db.query(models.HorarioAtencion).filter_by(profesional_id=profesional.id).order_by(models.HorarioAtencion.dia_semana.asc()).all()

    mapa_dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    return templates.TemplateResponse(request=request, name="config_horarios.html", context={"request": request, "horarios": horarios, "mapa_dias": mapa_dias})

@app.post("/admin/config/horarios")
async def guardar_horarios(request: Request, db: Session = Depends(get_db), usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    form = await request.form()
    profesional = db.query(models.Profesional).first()
    
    for i in range(7):
        horario = db.query(models.HorarioAtencion).filter_by(profesional_id=profesional.id, dia_semana=i).first()
        if horario:
            horario.abierto = form.get(f"abierto_{i}") == "1"
            
            ap1 = form.get(f"apertura_1_{i}")
            ci1 = form.get(f"cierre_1_{i}")
            if ap1: horario.apertura_1 = datetime.strptime(ap1, "%H:%M").time()
            if ci1: horario.cierre_1 = datetime.strptime(ci1, "%H:%M").time()
            
            ap2 = form.get(f"apertura_2_{i}")
            ci2 = form.get(f"cierre_2_{i}")
            horario.apertura_2 = datetime.strptime(ap2, "%H:%M").time() if ap2 else None
            horario.cierre_2 = datetime.strptime(ci2, "%H:%M").time() if ci2 else None
                
    db.commit()
    return RedirectResponse(url="/admin/config/horarios", status_code=303)

# --- 6. RUTAS DE EXCEPCIONES ---
@app.get("/admin/config/excepciones", response_class=HTMLResponse)
def panel_excepciones(request: Request, db: Session = Depends(get_db), usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    profesional = db.query(models.Profesional).first()
    excepciones = db.query(models.Excepcion).filter(
        models.Excepcion.profesional_id == profesional.id,
        models.Excepcion.fecha >= date.today()
    ).order_by(models.Excepcion.fecha.asc()).all()
    
    return templates.TemplateResponse(request=request, name="config_excepciones.html", context={"request": request, "excepciones": excepciones})

@app.post("/admin/config/excepciones")
async def agregar_excepcion(request: Request, db: Session = Depends(get_db), usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    form = await request.form()
    profesional = db.query(models.Profesional).first()
    
    nueva_excepcion = models.Excepcion(
        profesional_id=profesional.id,
        fecha=datetime.strptime(form.get("fecha"), "%Y-%m-%d").date(),
        motivo=form.get("motivo") or "Excepción"
    )
    
    if form.get("hora_inicio") and form.get("hora_fin"):
        nueva_excepcion.hora_inicio = datetime.strptime(form.get("hora_inicio"), "%H:%M").time()
        nueva_excepcion.hora_fin = datetime.strptime(form.get("hora_fin"), "%H:%M").time()

    db.add(nueva_excepcion)
    db.commit()
    return RedirectResponse(url="/admin/config/excepciones", status_code=303)

# --- 7. ELIMINAR EXCEPCIÓN ---
@app.post("/admin/config/excepciones/eliminar/{excepcion_id}")
def eliminar_excepcion(excepcion_id: int, db: Session = Depends(get_db), usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    excepcion = db.query(models.Excepcion).filter_by(id=excepcion_id).first()
    if excepcion:
        db.delete(excepcion)
        db.commit()
    return RedirectResponse(url="/admin/config/excepciones", status_code=303)

# --- CANCELAR TURNO ---
@app.post("/admin/turnos/cancelar/{turno_id}")
def cancelar_turno(turno_id: int, request: Request, db: Session = Depends(get_db), usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    turno = db.query(models.Turno).filter(models.Turno.id == turno_id).first()
    
    if turno:
        turno.estado = "cancelado"
        db.commit()
    
    referer = request.headers.get("referer", "/admin")
    return RedirectResponse(url=referer, status_code=303)