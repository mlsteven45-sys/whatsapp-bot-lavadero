"""
Scheduler: tareas programadas que corren en segundo plano cada 5 minutos.

1. RECORDATORIO (1 hora antes):
   - Busca citas que empiecen en los próximos 60-70 minutos
   - Le manda un mensaje de recordatorio al cliente con su resumen de cita
   - El cliente puede responder "confirmo" o "quiero reagendar" y Claude lo maneja natural

2. SEGUIMIENTO POST-SERVICIO (2 horas después):
   - Busca citas que terminaron hace entre 2 y 2.25 horas
   - Le manda un mensaje de agradecimiento preguntando cómo le fue

Usa un archivo JSON (notificaciones_enviadas.json) para llevar registro de
qué mensajes ya se enviaron por evento, evitando duplicados.
"""
import os
import json
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from whatsapp_api import send_text_message
import google_calendar

ARCHIVO_NOTIFICACIONES = os.path.join(os.path.dirname(__file__), "notificaciones_enviadas.json")

MINUTOS_ANTES_RECORDATORIO = 60     # cuándo enviar el recordatorio (minutos antes del servicio)
MINUTOS_VENTANA_RECORDATORIO = 10   # margen de búsqueda (para no perderse citas)
HORAS_DESPUES_SEGUIMIENTO = 2       # cuándo enviar el seguimiento post-servicio
MINUTOS_VENTANA_SEGUIMIENTO = 15    # margen de búsqueda del seguimiento


def _leer_notificaciones() -> dict:
    if not os.path.exists(ARCHIVO_NOTIFICACIONES):
        return {}
    try:
        with open(ARCHIVO_NOTIFICACIONES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _marcar_enviada(event_id: str, tipo: str):
    """Registra que ya se envió una notificación de cierto tipo para este evento."""
    data = _leer_notificaciones()
    if event_id not in data:
        data[event_id] = {}
    data[event_id][tipo] = datetime.utcnow().isoformat()
    with open(ARCHIVO_NOTIFICACIONES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _ya_enviada(event_id: str, tipo: str) -> bool:
    data = _leer_notificaciones()
    return tipo in data.get(event_id, {})


def _extraer_numero_cliente(descripcion: str) -> str | None:
    """Extrae el número de WhatsApp del cliente de la descripción del evento."""
    for linea in descripcion.splitlines():
        if "Cliente WhatsApp:" in linea:
            numero = linea.split("Cliente WhatsApp:")[-1].strip()
            if numero:
                return numero
    return None


def _obtener_eventos_en_rango(minutos_desde: int, minutos_hasta: int) -> list:
    """
    Obtiene todos los eventos del calendario de Motobon cuyo inicio esté
    entre 'minutos_desde' y 'minutos_hasta' minutos desde ahora.
    Devuelve lista de dicts con {id, summary, description, start, end}.
    """
    try:
        servicio = google_calendar._obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

        ahora_utc = datetime.utcnow()
        inicio_busqueda = ahora_utc + timedelta(minutes=minutos_desde)
        fin_busqueda = ahora_utc + timedelta(minutes=minutos_hasta)

        resultado = servicio.events().list(
            calendarId=calendar_id,
            timeMin=inicio_busqueda.isoformat() + "Z",
            timeMax=fin_busqueda.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        eventos = []
        for item in resultado.get("items", []):
            inicio_str = item.get("start", {}).get("dateTime")
            fin_str = item.get("end", {}).get("dateTime")
            if not inicio_str:
                continue
            eventos.append({
                "id": item["id"],
                "resumen": item.get("summary", "Cita"),
                "descripcion": item.get("description", ""),
                "inicio": datetime.fromisoformat(inicio_str),
                "fin": datetime.fromisoformat(fin_str) if fin_str else None,
            })
        return eventos

    except Exception as error:
        print("⚠️ Error buscando eventos en el scheduler:", error)
        return []


def _obtener_eventos_finalizados(horas_hace: float, ventana_minutos: int) -> list:
    """
    Obtiene eventos cuyo FIN estuvo entre 'horas_hace' horas y
    'horas_hace' horas + 'ventana_minutos' minutos en el pasado.
    """
    try:
        servicio = google_calendar._obtener_servicio_calendar()
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

        ahora_utc = datetime.utcnow()
        fin_min = ahora_utc - timedelta(hours=horas_hace, minutes=ventana_minutos)
        fin_max = ahora_utc - timedelta(hours=horas_hace)

        resultado = servicio.events().list(
            calendarId=calendar_id,
            timeMin=fin_min.isoformat() + "Z",
            timeMax=fin_max.isoformat() + "Z",
            singleEvents=True,
        ).execute()

        eventos = []
        for item in resultado.get("items", []):
            fin_str = item.get("end", {}).get("dateTime")
            if not fin_str:
                continue
            fin_dt = datetime.fromisoformat(fin_str)
            if fin_min <= fin_dt.replace(tzinfo=None) <= fin_max:
                eventos.append({
                    "id": item["id"],
                    "resumen": item.get("summary", "Cita"),
                    "descripcion": item.get("description", ""),
                    "fin": fin_dt,
                })
        return eventos

    except Exception as error:
        print("⚠️ Error buscando eventos finalizados en el scheduler:", error)
        return []


def enviar_recordatorios():
    """Busca citas próximas (~1 hora) y envía recordatorios a los clientes."""
    eventos = _obtener_eventos_en_rango(
        minutos_desde=MINUTOS_ANTES_RECORDATORIO,
        minutos_hasta=MINUTOS_ANTES_RECORDATORIO + MINUTOS_VENTANA_RECORDATORIO,
    )

    for evento in eventos:
        event_id = evento["id"]
        if _ya_enviada(event_id, "recordatorio"):
            continue

        numero_cliente = _extraer_numero_cliente(evento["descripcion"])
        if not numero_cliente:
            continue

        # Extraer nombre y servicio de la descripción para personalizar el mensaje
        nombre = "Cliente"
        servicio = "tu servicio"
        for linea in evento["descripcion"].splitlines():
            if linea.startswith("Nombre:"):
                nombre = linea.split("Nombre:")[-1].strip().split()[0]  # solo el primer nombre
            if linea.startswith("Servicio:"):
                servicio = linea.split("Servicio:")[-1].strip()

        hora_local = evento["inicio"] - timedelta(hours=5)  # UTC-5 Bogotá
        hora_texto = hora_local.strftime("%I:%M %p").lstrip("0")

        mensaje = (
            f"¡Hola {nombre}! 👋 Te recordamos que en aproximadamente una hora "
            f"tienes agendado tu *{servicio}* con nosotros a las *{hora_texto}*. "
            f"¿Confirmas tu asistencia? Si necesitas cambiar la hora, con gusto te ayudamos 🏍️"
        )

        try:
            send_text_message(numero_cliente, mensaje)
            _marcar_enviada(event_id, "recordatorio")
            print(f"✅ Recordatorio enviado a {numero_cliente} para evento {event_id}")
        except Exception as error:
            print(f"⚠️ Error enviando recordatorio a {numero_cliente}:", error)


def enviar_seguimiento_postservicio():
    """Busca citas que terminaron hace ~2 horas y envía mensaje de seguimiento."""
    eventos = _obtener_eventos_finalizados(
        horas_hace=HORAS_DESPUES_SEGUIMIENTO,
        ventana_minutos=MINUTOS_VENTANA_SEGUIMIENTO,
    )

    for evento in eventos:
        event_id = evento["id"]
        if _ya_enviada(event_id, "seguimiento"):
            continue

        numero_cliente = _extraer_numero_cliente(evento["descripcion"])
        if not numero_cliente:
            continue

        nombre = "Cliente"
        for linea in evento["descripcion"].splitlines():
            if linea.startswith("Nombre:"):
                nombre = linea.split("Nombre:")[-1].strip().split()[0]

        mensaje = (
            f"¡Hola {nombre}! 🏍️ Esperamos que hayas quedado muy contento con tu servicio hoy. "
            f"¿Cómo te fue? Tu opinión es muy importante para nosotros y nos ayuda a mejorar. "
            f"¡Gracias por confiar en *Motobon*! 🙌"
        )

        try:
            send_text_message(numero_cliente, mensaje)
            _marcar_enviada(event_id, "seguimiento")
            print(f"✅ Seguimiento enviado a {numero_cliente} para evento {event_id}")
        except Exception as error:
            print(f"⚠️ Error enviando seguimiento a {numero_cliente}:", error)


def iniciar_scheduler():
    """Arranca el scheduler en segundo plano. Se llama una vez al iniciar Flask."""
    scheduler = BackgroundScheduler(timezone="America/Bogota")
    scheduler.add_job(enviar_recordatorios, "interval", minutes=5, id="recordatorios")
    scheduler.add_job(enviar_seguimiento_postservicio, "interval", minutes=5, id="seguimiento")
    scheduler.start()
    print("✅ Scheduler iniciado: recordatorios y seguimiento post-servicio activos.")
    return scheduler
