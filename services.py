from datetime import datetime, date, time, timedelta
from typing import List
from sqlalchemy.orm import Session
from models import Turno, Servicio, HorarioAtencion, Excepcion

INTERVALO_MIN = 60  # Minutos entre cada turno (puedes ajustarlo si cambian los servicios)

def obtener_turnos_ocupados(db: Session, fecha: date) -> List[Turno]:
    inicio_dia = datetime.combine(fecha, time.min)
    fin_dia = datetime.combine(fecha, time.max)
    return db.query(Turno).filter(
        Turno.fecha_hora_inicio >= inicio_dia,
        Turno.fecha_hora_inicio <= fin_dia,
        Turno.estado == "confirmado"
    ).all()

def procesar_bloque(cursor, limite, ocupados, excepciones_del_dia, duracion_delta, paso, ahora):
    slots = []
    while cursor + duracion_delta <= limite:
        slot_inicio = cursor
        slot_fin = cursor + duracion_delta
        
        if slot_inicio < ahora:
            cursor += paso
            continue
            
        solapado = False
        for turno in ocupados:
            if slot_inicio < turno.fecha_hora_fin and slot_fin > turno.fecha_hora_inicio:
                solapado = True; break
                
        if not solapado:
            for exc in excepciones_del_dia:
                if exc.hora_inicio and exc.hora_fin:
                    if slot_inicio.time() < exc.hora_fin and slot_fin.time() > exc.hora_inicio:
                        solapado = True; break
                        
        if not solapado:
            slots.append(slot_inicio.strftime("%H:%M"))
        cursor += paso
    return slots

def calcular_horarios_disponibles(db: Session, fecha: date, duracion_min: int) -> List[str]:
    dia_semana = fecha.weekday()
    horario_dia = db.query(HorarioAtencion).filter(HorarioAtencion.dia_semana == dia_semana).first()

    if not horario_dia or not horario_dia.abierto:
        return []

    excepciones_del_dia = db.query(Excepcion).filter(Excepcion.fecha == fecha).all()
    for exc in excepciones_del_dia:
        if not exc.hora_inicio or not exc.hora_fin:
            return []  # Cerrado por excepción todo el día

    ocupados = obtener_turnos_ocupados(db, fecha)
    duracion_delta = timedelta(minutes=duracion_min)
    paso = timedelta(minutes=INTERVALO_MIN)
    ahora = datetime.now()
    slots_libres = []

    # Calcular slots del Turno 1
    cursor_1 = datetime.combine(fecha, horario_dia.apertura_1)
    limite_1 = datetime.combine(fecha, horario_dia.cierre_1)
    slots_libres.extend(procesar_bloque(cursor_1, limite_1, ocupados, excepciones_del_dia, duracion_delta, paso, ahora))

    # Calcular slots del Turno 2 (si existe)
    if horario_dia.apertura_2 and horario_dia.cierre_2:
        cursor_2 = datetime.combine(fecha, horario_dia.apertura_2)
        limite_2 = datetime.combine(fecha, horario_dia.cierre_2)
        slots_libres.extend(procesar_bloque(cursor_2, limite_2, ocupados, excepciones_del_dia, duracion_delta, paso, ahora))

    return slots_libres