"""
Guarda las citas agendadas en un archivo JSON local (citas.json).

Para producción real, esto se puede migrar a una base de datos
(SQLite/PostgreSQL) o incluso a Google Sheets, sin tener que cambiar
la lógica del resto del bot — solo esta función.
"""
import json
import os
from datetime import datetime

ARCHIVO_CITAS = os.path.join(os.path.dirname(__file__), "citas.json")


def _leer_citas() -> list:
    if not os.path.exists(ARCHIVO_CITAS):
        return []
    with open(ARCHIVO_CITAS, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_cita(numero: str, datos: dict):
    """Agrega una nueva cita al archivo citas.json."""
    citas = _leer_citas()
    citas.append({
        "numero_cliente": numero,
        "tipo_vehiculo": datos.get("tipo_vehiculo"),
        "servicio": datos.get("servicio"),
        "fecha": datos.get("fecha"),
        "hora": datos.get("hora"),
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    })
    with open(ARCHIVO_CITAS, "w", encoding="utf-8") as f:
        json.dump(citas, f, ensure_ascii=False, indent=2)
