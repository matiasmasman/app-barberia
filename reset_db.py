from database import engine, Base, SessionLocal
import models
from datetime import time
from auth import get_password_hash

print("Borrando base de datos de PostgreSQL...")
Base.metadata.drop_all(bind=engine)

print("Creando tablas limpias...")
Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    print("Cargando Comercio...")
    nuevo_comercio = models.Comercio(nombre="Barbería Juanpa", slug="barberia-juanpa")
    db.add(nuevo_comercio)
    db.commit()
    db.refresh(nuevo_comercio)

    print("Cargando Barberos...")
    pro_1 = models.Profesional(comercio_id=nuevo_comercio.id, nombre="Juanpa")
    pro_2 = models.Profesional(comercio_id=nuevo_comercio.id, nombre="Marcos")
    db.add_all([pro_1, pro_2])
    db.commit()
    db.refresh(pro_1)
    db.refresh(pro_2)

    print("Cargando Servicios y Horarios...")
    db.add_all([
        models.Servicio(comercio_id=nuevo_comercio.id, nombre="Corte", duracion_min=45, precio=6000),
        models.Servicio(comercio_id=nuevo_comercio.id, nombre="Corte + Barba", duracion_min=45, precio=8000),
    ])

    for i in range(7):
        db.add(models.HorarioAtencion(profesional_id=pro_1.id, dia_semana=i, abierto=(i != 6)))
        db.add(models.HorarioAtencion(
            profesional_id=pro_2.id, dia_semana=i, abierto=(i != 6),
            apertura_1=time(14, 0), cierre_1=time(21, 0),
            apertura_2=None, cierre_2=None
        ))
    db.commit()

    print("Cargando Usuarios de Acceso...")
    db.add_all([
        models.Usuario(username="superadmin", password_hash=get_password_hash("admin123"), rol="superadmin"),
        models.Usuario(username="juanpa", password_hash=get_password_hash("juanpa123"), rol="admin_local", comercio_id=nuevo_comercio.id),
        models.Usuario(username="marcos", password_hash=get_password_hash("marcos123"), rol="profesional", profesional_id=pro_2.id)
    ])
    db.commit()
    print("¡Éxito! Base de datos inicializada.")
finally:
    db.close()