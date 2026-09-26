from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Date, Time, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, time
from database import Base

class Servicio(Base):
    __tablename__ = "servicios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    duracion_min = Column(Integer, default=60)  # duración en minutos
    precio = Column(Float, nullable=False)

    turnos = relationship("Turno", back_populates="servicio")

class Turno(Base):
    __tablename__ = "turnos"

    id = Column(Integer, primary_key=True, index=True)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=False)
    cliente_nombre = Column(String(100), nullable=False)
    cliente_telefono = Column(String(20), nullable=False)
    fecha_hora_inicio = Column(DateTime, nullable=False, index=True)
    fecha_hora_fin = Column(DateTime, nullable=False)
    estado = Column(String(20), default="confirmado")  # confirmado, cancelado

    servicio = relationship("Servicio", back_populates="turnos")

class HorarioAtencion(Base):
    __tablename__ = "horarios_atencion"
    
    id = Column(Integer, primary_key=True, index=True)
    dia_semana = Column(Integer, unique=True) # 0 = Lunes, 6 = Domingo
    abierto = Column(Boolean, default=True)
    
    # Primer turno (Ej: 10:00 a 13:00)
    apertura_1 = Column(Time, default=time(10, 0))
    cierre_1 = Column(Time, default=time(13, 0))
    
    # Segundo turno opcional (Ej: 17:00 a 21:00). Si es nulo, trabajan solo un turno.
    apertura_2 = Column(Time, nullable=True, default=time(17, 0))
    cierre_2 = Column(Time, nullable=True, default=time(21, 0))

class Excepcion(Base):
    __tablename__ = "excepciones"
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=True) # Si es nulo, bloquea todo el día
    hora_fin = Column(Time, nullable=True)
    motivo = Column(String(200), default="No disponible")