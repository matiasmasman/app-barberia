from datetime import datetime, date, time, timedelta
from typing import List
from sqlalchemy.orm import Session
from models import Turno, HorarioAtencion, Excepcion, Profesional

# Ahora la agenda es una cuadrícula perfecta de 45 minutos
INTERVALO_MIN = 45  

def obtener_turnos_ocupados(db: Session, profesional_id: int, fecha: date) -> List[Turno]:
    inicio_dia = datetime.combine(fecha, time.min)
    fin_dia = datetime.combine(fecha, time.max)
    return db.query(Turno).filter(
        Turno.profesional_id == profesional_id,
        Turno.fecha_hora_inicio >= inicio_dia,
        Turno.fecha_hora_inicio <= fin_dia,
        Turno.estado == "confirmado"
    ).all()

def procesar_bloque(cursor, limite, ocupados, excepciones_del_dia, duracion_delta, paso, ahora):
    slots = []
    
    # EL CAMBIO MÁGICO: Mientras el turno EMPIECE antes del cierre (cursor < limite), lo permitimos.
    while cursor < limite:
        slot_inicio = cursor
        slot_fin = cursor + duracion_delta
        
        if slot_inicio < ahora:
            cursor += paso
            continue
            
        solapado = False
        for turno in ocupados:
            if slot_inicio < turno.fecha_hora_fin and slot_fin > turno.fecha_hora_inicio:
                solapado = True
                break
                
        if not solapado:
            for exc in excepciones_del_dia:
                if exc.hora_inicio and exc.hora_fin:
                    if slot_inicio.time() < exc.hora_fin and slot_fin.time() > exc.hora_inicio:
                        solapado = True
                        break
                        
        if not solapado:
            slots.append(slot_inicio.strftime("%H:%M"))
            
        # Como es bloque fijo, avanzamos siempre 45 minutos
        cursor += paso
        
    return slots

def calcular_horarios_disponibles(db: Session, profesional_id: int, fecha: date, duracion_min: int) -> List[str]:
    dia_semana = fecha.weekday()
    horario_dia = db.query(HorarioAtencion).filter(
        HorarioAtencion.profesional_id == profesional_id,
        HorarioAtencion.dia_semana == dia_semana
    ).first()

    if not horario_dia or not horario_dia.abierto:
        return []

    excepciones_del_dia = db.query(Excepcion).filter(
        Excepcion.profesional_id == profesional_id,
        Excepcion.fecha == fecha
    ).all()
    
    for exc in excepciones_del_dia:
        if not exc.hora_inicio or not exc.hora_fin:
            return []  # Cerrado por excepción todo el día

    ocupados = obtener_turnos_ocupados(db, profesional_id, fecha)
    
    duracion_delta = timedelta(minutes=INTERVALO_MIN)
    paso = timedelta(minutes=INTERVALO_MIN)
    ahora = datetime.now()
    slots_libres = []

    # Calcular slots del Turno 1
    if horario_dia.apertura_1 and horario_dia.cierre_1:
        cursor_1 = datetime.combine(fecha, horario_dia.apertura_1)
        limite_1 = datetime.combine(fecha, horario_dia.cierre_1)
        slots_libres.extend(procesar_bloque(cursor_1, limite_1, ocupados, excepciones_del_dia, duracion_delta, paso, ahora))

    # Calcular slots del Turno 2 (si existe)
    if horario_dia.apertura_2 and horario_dia.cierre_2:
        cursor_2 = datetime.combine(fecha, horario_dia.apertura_2)
        limite_2 = datetime.combine(fecha, horario_dia.cierre_2)
        slots_libres.extend(procesar_bloque(cursor_2, limite_2, ocupados, excepciones_del_dia, duracion_delta, paso, ahora))

    return slots_libres

def calcular_horarios_comercio(db: Session, comercio_id: int, fecha: date, duracion_min: int) -> List[str]:
    """
    Usa esta función cuando el cliente selecciona "Cualquier Barbero".
    Junta los horarios disponibles de todos los profesionales activos.
    """
    profesionales = db.query(Profesional).filter(
        Profesional.comercio_id == comercio_id, 
        Profesional.activo == True
    ).all()
    
    todos_los_slots = set() # Usamos un Set para que no haya horarios repetidos (ej: dos tienen libre a las 17:00)
    
    for p in profesionales:
        slots_pro = calcular_horarios_disponibles(db, p.id, fecha, duracion_min)
        todos_los_slots.update(slots_pro)
        
    # Ordenamos la lista resultante de menor a mayor (ej: 10:00, 10:45, 11:30)
    return sorted(list(todos_los_slots))