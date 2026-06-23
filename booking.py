"""
Guarda las citas agendadas en un archivo JSON local (citas.json) Y crea
el evento correspondiente en Google Calendar.

El archivo citas.json se mantiene como respaldo/registro: si Google
Calendar falla por cualquier motivo, la cita no se pierde, queda guardada
igual aquí. La función principal de cancelar/reagendar usa Google Calendar
directamente (no este archivo), así que sigue funcionando incluso después
de que el servidor se reinicie.
"""
import json
import os
from datetime import datetime

import google_calendar

ARCHIVO_CITAS = os.path.join(os.path.dirname(__file__), "citas.json")


def _leer_citas() -> list:
    if not os.path.exists(ARCHIVO_CITAS):
        return []
    with open(ARCHIVO_CITAS, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_cita(numero: str, datos: dict):
    """Crea el evento en Google Calendar y agrega un registro a citas.json."""
    event_id = google_calendar.crear_evento({**datos, "numero_cliente": numero})

    citas = _leer_citas()
    citas.append({
        "numero_cliente": numero,
        "nombre": datos.get("nombre"),
        "placa": datos.get("placa"),
        "tipo_vehiculo": datos.get("tipo_vehiculo"),
        "servicio": datos.get("servicio"),
        "fecha": datos.get("fecha"),
        "hora": datos.get("hora"),
        "event_id": event_id,
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    })
    with open(ARCHIVO_CITAS, "w", encoding="utf-8") as f:
        json.dump(citas, f, ensure_ascii=False, indent=2)
