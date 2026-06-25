"""
Integración con Google Calendar: crea, busca, cancela y reagenda eventos
para las citas de Motobon.

Usa una "Service Account" de Google (un usuario robot). Las credenciales
se leen desde GOOGLE_SERVICE_ACCOUNT_JSON, y el calendario de destino desde
GOOGLE_CALENDAR_ID.

Las funciones "_estructurado" reciben fecha en formato "YYYY-MM-DD" y hora
en formato 24h "HH:MM" — ya interpretadas por Claude a partir de lo que
escribió el cliente en lenguaje natural (ej: "el viernes a las 3pm").
Esto es más confiable que tratar de adivinar formatos de texto libre.

Si algo falla aquí, las funciones devuelven None/False/[] en vez de lanzar
un error — así un problema con Calendar nunca rompe la conversación del bot.
"""
import os
import json
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

import services_data

SCOPES = ["https://www.googleapis.com/auth/calendar"]
ZONA_HORARIA = "America/Bogota"
DURACION_CITA_MINUTOS = 60  # duración asumida de cada servicio, en minutos


def _obtener_servicio_calendar():
    """Crea el cliente autenticado de la API de Google Calendar."""
    credenciales_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(credenciales_json)
    credenciales = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=credenciales)


def _construir_datetime_estructurado(fecha_iso: str, hora_iso: str):
    """fecha_iso: 'YYYY-MM-DD', hora_iso: 'HH:MM' (24h). Devuelve datetime o None si es inválido."""
    try:
        return datetime.strptime(f"{fecha_iso.strip()} {hora_iso.strip()}", "%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return None


def _construir_resumen_y_descripcion(datos: dict):
    """Genera el título y la descripción del evento a partir de los datos del cliente."""
    nombre = datos.get("nombre", "Cliente sin nombre")
    placa = datos.get("placa", "Sin placa")
    servicio = datos.get("servicio", "Servicio")
    numero_cliente = datos.get("numero_cliente", "")

    precio = services_data.SERVICIOS.get("moto", {}).get(servicio)
    if precio is not None:
        precio_texto = f"${precio:,}".replace(",", ".") + " COP"
    else:
        precio_texto = "No especificado"

    resumen = f"Motobon: {nombre} - {servicio}"
    descripcion = (
        f"Nombre: {nombre}\n"
        f"Placa: {placa}\n"
        f"Servicio: {servicio}\n"
        f"Precio: {precio_texto}\n"
        f"Cliente WhatsApp: {numero_cliente}"
    )
    return resumen, descripcion


def crear_evento_estructurado(datos: dict, fecha_iso: str, hora_iso: str):
    """
    Crea un evento en Google Calendar a partir de fecha/hora ya estructuradas
    (formato YYYY-MM-DD y HH:MM 24h). Devuelve el ID del evento, o None si falló.
    """
    try:
        inicio = _construir_datetime_estructurado(fecha_iso, hora_iso)
        if inicio is None:
            print("⚠️ Google Calendar: fecha/hora estructurada inválida:", fecha_iso, hora_iso)
            return None

        fin = inicio + timedelta(minutes=DURACION_CITA_MINUTOS)
        resumen, descripcion = _construir_resumen_y_descripcion(datos)

        evento = {
            "summary": resumen,
            "description": descripcion,
            "start": {"dateTime": inicio.isoformat(), "timeZone": ZONA_HORARIA},
            "end": {"dateTime": fin.isoformat(), "timeZone": ZONA_HORARIA},
        }

        servicio_calendar = _obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        evento_creado = servicio_calendar.events().insert(calendarId=calendar_id, body=evento).execute()
        return evento_creado.get("id")

    except Exception as error:
        print("⚠️ Error al crear evento en Google Calendar:", error)
        return None


def buscar_eventos_por_cliente(numero_cliente: str, max_resultados: int = 10) -> list:
    """
    Busca eventos futuros que mencionen el número de este cliente.
    Devuelve una lista de dicts: [{"id", "resumen", "inicio" (datetime)}, ...]
    """
    try:
        servicio_calendar = _obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        ahora = datetime.utcnow().isoformat() + "Z"

        resultado = servicio_calendar.events().list(
            calendarId=calendar_id,
            timeMin=ahora,
            q=numero_cliente,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_resultados,
        ).execute()

        eventos = []
        for item in resultado.get("items", []):
            inicio_str = item.get("start", {}).get("dateTime")
            if not inicio_str:
                continue
            eventos.append({
                "id": item["id"],
                "resumen": item.get("summary", "Cita"),
                "inicio": datetime.fromisoformat(inicio_str),
            })
        return eventos

    except Exception as error:
        print("⚠️ Error al buscar eventos en Google Calendar:", error)
        return []


def eliminar_evento(event_id: str) -> bool:
    """Elimina un evento del calendario. Devuelve True si lo logró."""
    try:
        servicio_calendar = _obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        servicio_calendar.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True
    except Exception as error:
        print("⚠️ Error al eliminar evento en Google Calendar:", error)
        return False


def actualizar_evento_estructurado(event_id: str, fecha_iso: str, hora_iso: str) -> bool:
    """Cambia la fecha/hora de un evento existente. Devuelve True si lo logró."""
    try:
        inicio = _construir_datetime_estructurado(fecha_iso, hora_iso)
        if inicio is None:
            return False
        fin = inicio + timedelta(minutes=DURACION_CITA_MINUTOS)

        servicio_calendar = _obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        servicio_calendar.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={
                "start": {"dateTime": inicio.isoformat(), "timeZone": ZONA_HORARIA},
                "end": {"dateTime": fin.isoformat(), "timeZone": ZONA_HORARIA},
            },
        ).execute()
        return True
    except Exception as error:
        print("⚠️ Error al actualizar evento en Google Calendar:", error)
        return False
