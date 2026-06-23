"""
Guarda las citas agendadas en un archivo JSON local (citas.json) Y crea
el evento correspondiente en Google Calendar.

El archivo citas.json se mantiene como respaldo: si Google Calendar falla
por cualquier motivo, la cita no se pierde, queda guardada igual aquí.
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
    """Agrega una nueva cita a citas.json y crea el evento en Google Calendar."""
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

    # Si esto falla, no interrumpe el flujo del bot (la cita ya quedó guardada arriba)
    google_calendar.crear_evento({**datos, "numero_cliente": numero})
