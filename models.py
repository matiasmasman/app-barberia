from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Date, Time, Boolean
from sqlalchemy.orm import relationship
from datetime import time
from database import Base

class Comercio(Base):
    """
    Esta es la tabla clave del SaaS. Cada cliente tuyo (la barbería, la chica de las uñas)
    es un 'Comercio' distinto.
    """
    __tablename__ = "comercios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    # El slug es para la URL, ej: "barberia-juan" -> tusistema.com/barberia-juan
    slug = Column(String(100), unique=True, index=True, nullable=False) 
    activo = Column(Boolean, default=True)

    # Relaciones
    profesionales = relationship("Profesional", back_populates="comercio")
    servicios = relationship("Servicio", back_populates="comercio")

class Profesional(Base):
    """
    Reemplaza a 'Barbero'. Puede ser un peluquero, masajista, médico, etc.
    """
    __tablename__ = "profesionales"

    id = Column(Integer, primary_key=True, index=True)
    comercio_id = Column(Integer, ForeignKey("comercios.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    telegram_chat_id = Column(String(50), nullable=True) # Para sus alertas personales
    activo = Column(Boolean, default=True)

    # Relaciones
    comercio = relationship("Comercio", back_populates="profesionales")
    turnos = relationship("Turno", back_populates="profesional")
    horarios = relationship("HorarioAtencion", back_populates="profesional")
    excepciones = relationship("Excepcion", back_populates="profesional")

class Servicio(Base):
    __tablename__ = "servicios"

    id = Column(Integer, primary_key=True, index=True)
    comercio_id = Column(Integer, ForeignKey("comercios.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    duracion_min = Column(Integer, default=60)
    precio = Column(Float, nullable=False)

    comercio = relationship("Comercio", back_populates="servicios")
    turnos = relationship("Turno", back_populates="servicio")

class Turno(Base):
    __tablename__ = "turnos"

    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesionales.id"), nullable=False)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=False)
    
    cliente_nombre = Column(String(100), nullable=False)
    cliente_telefono = Column(String(20), nullable=False)
    fecha_hora_inicio = Column(DateTime, nullable=False, index=True)
    fecha_hora_fin = Column(DateTime, nullable=False)
    estado = Column(String(20), default="confirmado") 

    profesional = relationship("Profesional", back_populates="turnos")
    servicio = relationship("Servicio", back_populates="turnos")

class HorarioAtencion(Base):
    __tablename__ = "horarios_atencion"
    
    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesionales.id"), nullable=False)
    dia_semana = Column(Integer) # Ya no es unique=True
    abierto = Column(Boolean, default=True)
    
    apertura_1 = Column(Time, default=time(10, 0))
    cierre_1 = Column(Time, default=time(13, 0))
    apertura_2 = Column(Time, nullable=True, default=time(17, 0))
    cierre_2 = Column(Time, nullable=True, default=time(21, 0))

    profesional = relationship("Profesional", back_populates="horarios")

class Excepcion(Base):
    __tablename__ = "excepciones"
    
    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesionales.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=True)
    hora_fin = Column(Time, nullable=True)
    motivo = Column(String(200), default="No disponible")

    profesional = relationship("Profesional", back_populates="excepciones")

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    rol = Column(String(20), nullable=False) # Roles: 'superadmin', 'admin_local', 'profesional'
    
    # Relaciones de contexto (pueden ser nulas dependiendo del rol)
    comercio_id = Column(Integer, ForeignKey("comercios.id"), nullable=True)
    profesional_id = Column(Integer, ForeignKey("profesionales.id"), nullable=True)

    comercio = relationship("Comercio")
    profesional = relationship("Profesional")