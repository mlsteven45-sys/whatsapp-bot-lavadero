"""
Integración con Google Calendar: crea un evento por cada cita confirmada.

Usa una "Service Account" de Google (un usuario robot) en lugar de pedirle
login a una persona. Las credenciales se leen desde la variable de entorno
GOOGLE_SERVICE_ACCOUNT_JSON (el contenido completo del archivo .json que
se descargó de Google Cloud), y el calendario de destino desde la variable
GOOGLE_CALENDAR_ID.

Si algo falla aquí (credenciales mal puestas, fecha no interpretable, etc.),
la función crear_evento() devuelve False en vez de lanzar un error — así
un problema con Calendar nunca rompe la conversación del bot por WhatsApp.
La cita siempre queda guardada en citas.json sin importar si esto funciona.
"""
import os
import json
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
ZONA_HORARIA = "America/Bogota"
DURACION_CITA_MINUTOS = 60  # duración asumida de cada servicio, en minutos

# Formatos de fecha/hora que el bot intenta reconocer del texto que escribe el cliente.
FORMATOS_FECHA = ["%d/%m/%Y", "%d-%m-%Y"]
FORMATOS_HORA = ["%I:%M %p", "%I:%M%p", "%H:%M"]


def _obtener_servicio_calendar():
    """Crea el cliente autenticado de la API de Google Calendar."""
    credenciales_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(credenciales_json)
    credenciales = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=credenciales)


def _parsear_fecha_hora(fecha_texto: str, hora_texto: str):
    """
    Convierte el texto libre de fecha y hora (ej: "25/06/2026", "3:00 PM")
    en un datetime real. Devuelve None si no logra interpretarlo.
    """
    fecha = None
    for formato in FORMATOS_FECHA:
        try:
            fecha = datetime.strptime(fecha_texto.strip(), formato)
            break
        except ValueError:
            continue
    if fecha is None:
        return None

    hora = None
    texto_hora_normalizado = hora_texto.strip().upper().replace(".", "")
    for formato in FORMATOS_HORA:
        try:
            hora = datetime.strptime(texto_hora_normalizado, formato)
            break
        except ValueError:
            continue
    if hora is None:
        return None

    return fecha.replace(hour=hora.hour, minute=hora.minute)


def crear_evento(datos: dict) -> bool:
    """
    Crea un evento en el Google Calendar de Motobon a partir de los datos
    de la cita (servicio, fecha, hora, número del cliente).
    Devuelve True si se creó bien, False si algo falló.
    """
    try:
        inicio = _parsear_fecha_hora(datos.get("fecha", ""), datos.get("hora", ""))
        if inicio is None:
            print("⚠️ Google Calendar: no se pudo interpretar fecha/hora:", datos)
            return False

        fin = inicio + timedelta(minutes=DURACION_CITA_MINUTOS)

        evento = {
            "summary": f"Cita Motobon - {datos.get('servicio', 'Servicio')}",
            "description": f"Cliente WhatsApp: {datos.get('numero_cliente', '')}",
            "start": {"dateTime": inicio.isoformat(), "timeZone": ZONA_HORARIA},
            "end": {"dateTime": fin.isoformat(), "timeZone": ZONA_HORARIA},
        }

        servicio_calendar = _obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        servicio_calendar.events().insert(calendarId=calendar_id, body=evento).execute()
        return True

    except Exception as error:
        print("⚠️ Error al crear evento en Google Calendar:", error)
        return False
