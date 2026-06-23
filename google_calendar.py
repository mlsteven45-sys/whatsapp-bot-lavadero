"""
Integración con Google Calendar: crea, busca, cancela y reagenda eventos
para las citas de Motobon.

Usa una "Service Account" de Google (un usuario robot) en lugar de pedirle
login a una persona. Las credenciales se leen desde la variable de entorno
GOOGLE_SERVICE_ACCOUNT_JSON, y el calendario de destino desde la variable
GOOGLE_CALENDAR_ID.

Si algo falla aquí (credenciales mal puestas, fecha no interpretable, etc.),
las funciones devuelven None/False/[] en vez de lanzar un error — así un
problema con Calendar nunca rompe la conversación del bot por WhatsApp.
"""
import os
import json
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
ZONA_HORARIA = "America/Bogota"
DURACION_CITA_MINUTOS = 60  # duración asumida de cada servicio, en minutos

FORMATOS_FECHA = ["%d/%m/%Y", "%d-%m-%Y"]
FORMATOS_HORA = ["%I:%M %p", "%I:%M%p", "%H:%M"]


def _obtener_servicio_calendar():
    """Crea el cliente autenticado de la API de Google Calendar."""
    credenciales_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(credenciales_json)
    credenciales = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=credenciales)


def _parsear_fecha_hora(fecha_texto: str, hora_texto: str):
    """Convierte texto libre de fecha y hora en un datetime real, o None si falla."""
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


def _construir_resumen_y_descripcion(datos: dict):
    """Genera el título y la descripción del evento a partir de los datos del cliente."""
    nombre = datos.get("nombre", "Cliente sin nombre")
    placa = datos.get("placa", "Sin placa")
    servicio = datos.get("servicio", "Servicio")
    numero_cliente = datos.get("numero_cliente", "")

    resumen = f"Motobon: {nombre} - {servicio}"
    descripcion = (
        f"Nombre: {nombre}\n"
        f"Placa: {placa}\n"
        f"Servicio: {servicio}\n"
        f"Cliente WhatsApp: {numero_cliente}"
    )
    return resumen, descripcion


def crear_evento(datos: dict):
    """
    Crea un evento en el Google Calendar de Motobon a partir de los datos
    de la cita (nombre, placa, servicio, fecha, hora, número del cliente).
    Devuelve el ID del evento creado, o None si algo falló.
    """
    try:
        inicio = _parsear_fecha_hora(datos.get("fecha", ""), datos.get("hora", ""))
        if inicio is None:
            print("⚠️ Google Calendar: no se pudo interpretar fecha/hora:", datos)
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
    Busca eventos futuros que mencionen el número de este cliente (se
    guarda en la descripción de cada evento al crearlo).
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


def actualizar_evento(event_id: str, fecha_texto: str, hora_texto: str) -> bool:
    """Cambia la fecha/hora de un evento existente. Devuelve True si lo logró."""
    try:
        inicio = _parsear_fecha_hora(fecha_texto, hora_texto)
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
