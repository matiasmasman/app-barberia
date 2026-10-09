from database import engine, Base, SessionLocal
import models
from datetime import time
from auth import get_password_hash # NUEVO: Importamos el encriptador

# 1. Destruimos todo (Borrado nuclear)
print("Borrando base de datos de PostgreSQL...")
Base.metadata.drop_all(bind=engine)

# 2. Creamos tablas vacías
print("Creando tablas limpias...")
Base.metadata.create_all(bind=engine)

# 3. Cargamos los datos exactos
db = SessionLocal()
try:
    # NUEVO: Creamos SOLO tu usuario root/superadmin para no quedar afuera del sistema
    print("Cargando Superadmin...")
    superadmin = models.Usuario(
        username="superadmin", 
        password_hash=get_password_hash("admin123"), 
        rol="superadmin"
    )
    db.add(superadmin)
    db.commit()

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

    print("Cargando Servicios...")
    db.add_all([
        models.Servicio(comercio_id=nuevo_comercio.id, nombre="Corte", duracion_min=45, precio=6000),
        models.Servicio(comercio_id=nuevo_comercio.id, nombre="Corte + Barba", duracion_min=45, precio=8000),
    ])

    print("Cargando Horarios...")
    for i in range(7):
        # Juanpa: Trabaja de 10 a 13 y de 17 a 21 (Lunes a Sábado)
        db.add(models.HorarioAtencion(profesional_id=pro_1.id, dia_semana=i, abierto=(i != 6)))
        
        # Marcos: Solo turno tarde de 14 a 21 (Lunes a Sábado)
        db.add(models.HorarioAtencion(
            profesional_id=pro_2.id, 
            dia_semana=i, 
            abierto=(i != 6),
            apertura_1=time(14, 0),
            cierre_1=time(21, 0),
            apertura_2=None,  # No corta, sigue de largo
            cierre_2=None
        ))
    db.commit()
    print("¡Éxito! Base de datos reseteada e inicializada.")
finally:
    db.close()