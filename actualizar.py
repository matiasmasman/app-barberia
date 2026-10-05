from database import SessionLocal
import models

db = SessionLocal()

servicios = db.query(models.Servicio).all()
for s in servicios:
    s.duracion_min = 45

db.commit()
print("¡Listo! Todos los servicios ahora duran 45 minutos en la base de datos.")
db.close()