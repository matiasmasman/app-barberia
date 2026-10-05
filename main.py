import secrets
import json
from datetime import datetime, date, time, timedelta
from fastapi import FastAPI, Depends, Form, Request, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models
import services

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestor de Turnos Peluquería")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic()

def verificar_admin(credentials: HTTPBasicCredentials = Depends(security)):
    usuario_valido = secrets.compare_digest(credentials.username, "admin")
    pass_valido = secrets.compare_digest(credentials.password, "44905416")

    if not (usuario_valido and pass_valido):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso denegado",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.on_event("startup")
def startup_populate():
    db = next(get_db())
    if not db.query(models.Servicio).first():
        db.add_all([
            models.Servicio(nombre="Corte", duracion_min=45, precio=0),
            models.Servicio(nombre="Corte + Barba", duracion_min=45, precio=0),
        ])
        db.commit()

# 1. Página principal de reserva (para clientes)
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    servicios = db.query(models.Servicio).all()
    hoy = date.today().isoformat()

    # Buscar qué días fijos están cerrados (Ej: Domingos)
    horarios = db.query(models.HorarioAtencion).all()
    dias_js = []
    if horarios:
        dias_cerrados_python = [h.dia_semana for h in horarios if not h.abierto]
        # Transformar día de Python (0=Lunes) a JS (0=Domingo)
        dias_js = [(d + 1) % 7 for d in dias_cerrados_python]
    else:
        dias_js = [0] 

    # Buscar excepciones de día completo (sin hora de inicio)
    excepciones = db.query(models.Excepcion).filter(models.Excepcion.hora_inicio == None).all()
    fechas_cerradas = [e.fecha.isoformat() for e in excepciones]

    return templates.TemplateResponse(
        request=request,
        name="reservar.html",
        context={
            "request": request,
            "servicios": servicios,
            "hoy": hoy,
            "dias_js": json.dumps(dias_js),
            "fechas_cerradas": json.dumps(fechas_cerradas),
        },
    )

# 2. Endpoint API de disponibilidad
@app.get("/api/disponibilidad")
def ver_disponibilidad(fecha: str, servicio_id: int, db: Session = Depends(get_db)):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    servicio = db.query(models.Servicio).filter(models.Servicio.id == servicio_id).first()
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    slots = services.calcular_horarios_disponibles(db, fecha_obj, servicio.duracion_min)
    return {"disponibles": slots}

# 3. Procesar reserva de turno
@app.post("/reservar")
def procesar_reserva(
    cliente_nombre: str = Form(...),
    cliente_telefono: str = Form(...),
    servicio_id: int = Form(...),
    fecha: str = Form(...),
    hora: str = Form(...),
    db: Session = Depends(get_db),
):
    if not cliente_telefono.isdigit() or len(cliente_telefono) != 10:
        raise HTTPException(status_code=400, detail="Número inválido.")

    servicio = db.query(models.Servicio).filter(models.Servicio.id == servicio_id).first()
    inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    
    import datetime as dt 
    fin = inicio + dt.timedelta(minutes=servicio.duracion_min)

    ocupados = services.obtener_turnos_ocupados(db, inicio.date())
    for t in ocupados:
        if inicio < t.fecha_hora_fin and fin > t.fecha_hora_inicio:
            raise HTTPException(status_code=400, detail="El horario acaba de ser ocupado. Elegí otro.")

    nuevo_turno = models.Turno(
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
    db: Session = Depends(get_db),
    admin: str = Depends(verificar_admin),
):
    # Función interna para armar la estructura de una semana dada una fecha
    def armar_semana(fecha_referencia):
        inicio_sem = fecha_referencia - timedelta(days=fecha_referencia.weekday())
        fin_sem = inicio_sem + timedelta(days=6)
        
        turnos_sem = db.query(models.Turno).filter(
            models.Turno.fecha_hora_inicio >= datetime.combine(inicio_sem, time.min),
            models.Turno.fecha_hora_inicio <= datetime.combine(fin_sem, time.max),
            models.Turno.estado == "confirmado"
        ).order_by(models.Turno.fecha_hora_inicio.asc()).all()

        horarios = db.query(models.HorarioAtencion).all()
        excepciones = db.query(models.Excepcion).filter(
            models.Excepcion.fecha >= inicio_sem,
            models.Excepcion.fecha <= fin_sem
        ).all()

        mapa_dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        semana_estructurada = []

        for i in range(7):
            dia_actual = inicio_sem + timedelta(days=i)

            if dia_actual < date.today():
                continue
            
            horario = next((h for h in horarios if h.dia_semana == dia_actual.weekday()), None)
            if horario and not horario.abierto:
                continue
                
            exc = next((e for e in excepciones if e.fecha == dia_actual and not e.hora_inicio), None)
            if exc:
                continue

            turnos_dia = [t for t in turnos_sem if t.fecha_hora_inicio.date() == dia_actual]
            
            semana_estructurada.append({
                "fecha_str": dia_actual.strftime("%d/%m"),
                "nombre_dia": mapa_dias[dia_actual.weekday()],
                "es_hoy": dia_actual == date.today(),
                "turnos": turnos_dia
            })
            
        return semana_estructurada, inicio_sem, fin_sem

    # Lógica principal de salto automático
    fecha_ref = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else date.today()
    semana_estructurada, inicio_semana, fin_semana = armar_semana(fecha_ref)

    # Si la semana está vacía Y el usuario no eligió manualmente la fecha (entró por defecto),
    # saltamos automáticamente a la próxima semana.
    if not semana_estructurada and not fecha:
        fecha_ref = fecha_ref + timedelta(days=(7 - fecha_ref.weekday())) # Salto al próximo Lunes
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
            "hoy_esta_en_semana": inicio_semana <= date.today() <= fin_semana
        },
    )

# --- 5. RUTAS DE HORARIO HABITUAL ---
@app.get("/admin/config/horarios", response_class=HTMLResponse)
def panel_horarios(request: Request, db: Session = Depends(get_db), admin: str = Depends(verificar_admin)):
    horarios = db.query(models.HorarioAtencion).order_by(models.HorarioAtencion.dia_semana.asc()).all()
    if not horarios:
        for i in range(7):
            # Por defecto: Lunes a Sábado abierto, Domingo cerrado
            nuevo_dia = models.HorarioAtencion(dia_semana=i, abierto=(i != 6))
            db.add(nuevo_dia)
        db.commit()
        horarios = db.query(models.HorarioAtencion).order_by(models.HorarioAtencion.dia_semana.asc()).all()

    mapa_dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    return templates.TemplateResponse(request=request, name="config_horarios.html", context={"request": request, "horarios": horarios, "mapa_dias": mapa_dias})

@app.post("/admin/config/horarios")
async def guardar_horarios(request: Request, db: Session = Depends(get_db), admin: str = Depends(verificar_admin)):
    form = await request.form()
    
    for i in range(7):
        horario = db.query(models.HorarioAtencion).filter_by(dia_semana=i).first()
        if horario:
            horario.abierto = form.get(f"abierto_{i}") == "1"
            
            # Turno 1
            ap1 = form.get(f"apertura_1_{i}")
            ci1 = form.get(f"cierre_1_{i}")
            if ap1: horario.apertura_1 = datetime.strptime(ap1, "%H:%M").time()
            if ci1: horario.cierre_1 = datetime.strptime(ci1, "%H:%M").time()
            
            # Turno 2 (Puede venir vacío)
            ap2 = form.get(f"apertura_2_{i}")
            ci2 = form.get(f"cierre_2_{i}")
            horario.apertura_2 = datetime.strptime(ap2, "%H:%M").time() if ap2 else None
            horario.cierre_2 = datetime.strptime(ci2, "%H:%M").time() if ci2 else None
                
    db.commit()
    return RedirectResponse(url="/admin/config/horarios", status_code=303)

# --- 6. RUTAS DE EXCEPCIONES ---
@app.get("/admin/config/excepciones", response_class=HTMLResponse)
def panel_excepciones(request: Request, db: Session = Depends(get_db), admin: str = Depends(verificar_admin)):
    excepciones = db.query(models.Excepcion).filter(models.Excepcion.fecha >= date.today()).order_by(models.Excepcion.fecha.asc()).all()
    return templates.TemplateResponse(request=request, name="config_excepciones.html", context={"request": request, "excepciones": excepciones})

@app.post("/admin/config/excepciones")
async def agregar_excepcion(request: Request, db: Session = Depends(get_db), admin: str = Depends(verificar_admin)):
    form = await request.form()
    
    nueva_excepcion = models.Excepcion(
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
def eliminar_excepcion(excepcion_id: int, db: Session = Depends(get_db), admin: str = Depends(verificar_admin)):
    excepcion = db.query(models.Excepcion).filter_by(id=excepcion_id).first()
    if excepcion:
        db.delete(excepcion)
        db.commit()
    return RedirectResponse(url="/admin/config/excepciones", status_code=303)

# --- NUEVA RUTA: Cancelar Turno ---
@app.post("/admin/turnos/cancelar/{turno_id}")
def cancelar_turno(turno_id: int, request: Request, db: Session = Depends(get_db), admin: str = Depends(verificar_admin)):
    turno = db.query(models.Turno).filter(models.Turno.id == turno_id).first()
    
    if turno:
        turno.estado = "cancelado"
        db.commit()
    
    # Redirigir de vuelta a la misma vista que estaba mirando
    referer = request.headers.get("referer", "/admin")
    return RedirectResponse(url=referer, status_code=303)