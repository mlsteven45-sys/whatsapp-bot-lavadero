"""
Guarda las citas agendadas en citas.json (respaldo/registro) Y crea el
evento correspondiente en Google Calendar.

citas.json es solo un respaldo: cancelar/reagendar usa Google Calendar
directamente, así que sigue funcionando aunque el servidor se reinicie.
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


def guardar_cita_estructurada(numero: str, datos: dict, fecha_iso: str, hora_iso: str):
    """
    Crea el evento en Google Calendar y agrega un registro a citas.json.
    fecha_iso: "YYYY-MM-DD", hora_iso: "HH:MM" (24h) — ya interpretados por Claude.
    Devuelve el event_id si se creó bien, o None si falló.
    """
    event_id = google_calendar.crear_evento_estructurado({**datos, "numero_cliente": numero}, fecha_iso, hora_iso)

    citas = _leer_citas()
    citas.append({
        "numero_cliente": numero,
        "nombre": datos.get("nombre"),
        "placa": datos.get("placa"),
        "tipo_vehiculo": datos.get("tipo_vehiculo"),
        "servicio": datos.get("servicio"),
        "fecha": fecha_iso,
        "hora": hora_iso,
        "event_id": event_id,
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    })
    with open(ARCHIVO_CITAS, "w", encoding="utf-8") as f:
        json.dump(citas, f, ensure_ascii=False, indent=2)

    return event_id
