"""
Punto central del bot conversacional: usa la API de Claude para entender
lenguaje natural y decidir cuándo ejecutar acciones reales (agendar,
cancelar, enviar PQR, mostrar fotos, avisar al dueño) mediante "herramientas"
(tool use). Las acciones reales viven en booking.py, google_calendar.py y
whatsapp_api.py — Claude solo decide cuándo usarlas.

El historial de conversación se guarda en memoria por número de WhatsApp
(se reinicia si el servidor se reinicia; aceptable para esta escala).
"""
import os
import threading
from datetime import datetime, timedelta

import anthropic

import services_data
import booking
import google_calendar
import bot_control
from whatsapp_api import send_text_message, send_image_message

MODELO = "claude-haiku-4-5"
MAX_MENSAJES_HISTORIAL = 20  # cuántos mensajes recientes recordamos por cliente

historial_conversaciones = {}  # { "numero": [ {"role":..., "content":...}, ... ] }

_cliente_anthropic = None

# Un "candado" por número de WhatsApp: evita que dos mensajes del MISMO
# cliente se procesen al mismo tiempo en hilos distintos (por ejemplo, si
# Meta llega a reintentar la entrega de un mensaje). Clientes distintos sí
# se siguen procesando en paralelo sin problema.
_candados_por_numero = {}
_candado_global = threading.Lock()


def _obtener_candado(numero: str) -> threading.Lock:
    with _candado_global:
        if numero not in _candados_por_numero:
            _candados_por_numero[numero] = threading.Lock()
        return _candados_por_numero[numero]


def _get_cliente():
    global _cliente_anthropic
    if _cliente_anthropic is None:
        _cliente_anthropic = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _cliente_anthropic


def _fecha_actual_bogota() -> str:
    """Fecha y día de la semana de hoy en Colombia (UTC-5, sin horario de verano)."""
    ahora = datetime.utcnow() - timedelta(hours=5)
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return f"{ahora.strftime('%Y-%m-%d')} ({dias[ahora.weekday()]})"


def _construir_system_prompt() -> str:
    return f"""Eres el asistente virtual de {services_data.NOMBRE_NEGOCIO}, un negocio de lavado y detallado de motos en Medellín, Colombia. Hablas por WhatsApp directamente con los clientes.

INFORMACIÓN DEL NEGOCIO:
- Horario de atención: {services_data.HORARIO_ATENCION}
- Ubicación: {services_data.UBICACION}
- Servicios y precios:
{services_data.formatear_precios("moto")}

FECHA DE HOY: {_fecha_actual_bogota()}

CÓMO DEBES COMPORTARTE:
- Habla como una persona real y amable, en español colombiano natural, cercano pero profesional. No suenes robótico ni repitas frases de menú.
- Usa emojis con moderación, solo cuando se sientan naturales.
- Respuestas cortas y claras, como en una conversación real de WhatsApp (no párrafos largos).
- Si preguntan por servicios o precios, responde directamente con la información de arriba. Si el cliente parece interesado, ofrece mostrarle fotos con la herramienta mostrar_fotos_servicios.
- Para agendar una cita necesitas 4 datos: nombre completo, placa de la moto, servicio deseado, fecha y hora. Pregúntalos de forma natural (el cliente puede darlos todos de una vez o por partes). Antes de llamar a agendar_cita, repite el resumen y espera que el cliente confirme explícitamente.
- Las fechas/horas que le pases a las herramientas deben ir en formato fecha="YYYY-MM-DD" y hora="HH:MM" en 24 horas. Tú interpretas lo que diga el cliente (ej: "el viernes a las 3pm", "mañana en la tarde") usando la fecha de hoy como referencia, y conviertes a ese formato.
- Si el cliente quiere cancelar o cambiar una cita, usa buscar_mis_citas primero, muéstrale sus citas de forma natural, y confirma cuál antes de usar cancelar_cita o reagendar_cita.
- Si el cliente tiene una queja, reclamo o petición (PQR), usa enviar_pqr con su mensaje.
- Si el cliente pide hablar con una persona/asesor humano, usa solicitar_asesor.
- REGLA IMPORTANTE: nunca le digas al cliente que algo ya se hizo (agendar, cancelar, reagendar, avisar al dueño, enviar una queja) sin haber llamado realmente a la herramienta correspondiente primero. Si tienes duda de si ya se ejecutó, vuelve a llamarla antes de confirmar.
- Nunca inventes información que no tengas. Si no sabes algo, dilo con honestidad."""


HERRAMIENTAS = [
    {
        "name": "mostrar_fotos_servicios",
        "description": "Envía al cliente fotos de los servicios disponibles con sus precios. Úsala cuando el cliente quiera ver cómo se ven los servicios.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "agendar_cita",
        "description": "Crea una cita en el calendario del negocio. Solo úsala después de confirmar todos los datos con el cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo del cliente"},
                "placa": {"type": "string", "description": "Placa de la moto"},
                "servicio": {"type": "string", "description": "Nombre exacto del servicio elegido"},
                "fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                "hora": {"type": "string", "description": "Hora en formato 24h HH:MM"},
            },
            "required": ["nombre", "placa", "servicio", "fecha", "hora"],
        },
    },
    {
        "name": "buscar_mis_citas",
        "description": "Busca las próximas citas agendadas de este cliente. Úsala antes de cancelar o reagendar.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancelar_cita",
        "description": "Cancela una cita existente, identificada por su event_id (obtenido con buscar_mis_citas).",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "reagendar_cita",
        "description": "Cambia la fecha/hora de una cita existente, identificada por su event_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "fecha": {"type": "string", "description": "Nueva fecha YYYY-MM-DD"},
                "hora": {"type": "string", "description": "Nueva hora 24h HH:MM"},
            },
            "required": ["event_id", "fecha", "hora"],
        },
    },
    {
        "name": "enviar_pqr",
        "description": "Envía una petición, queja o reclamo del cliente directamente al dueño del negocio.",
        "input_schema": {
            "type": "object",
            "properties": {"mensaje": {"type": "string"}},
            "required": ["mensaje"],
        },
    },
    {
        "name": "solicitar_asesor",
        "description": "Avisa al dueño del negocio que este cliente quiere hablar con una persona real.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _ejecutar_herramienta(nombre_herramienta: str, args: dict, numero: str) -> str:
    """Ejecuta la acción real y devuelve un texto de resultado para que Claude lo use en su respuesta."""
    try:
        if nombre_herramienta == "mostrar_fotos_servicios":
            for nombre_serv, precio in services_data.SERVICIOS["moto"].items():
                precio_fmt = f"{precio:,}".replace(",", ".")
                url_imagen = services_data.url_imagen_servicio(nombre_serv)
                if url_imagen:
                    send_image_message(numero, url_imagen, caption=f"{nombre_serv}\n${precio_fmt} COP")
            return "Fotos enviadas correctamente al cliente."

        elif nombre_herramienta == "agendar_cita":
            datos = {
                "nombre": args["nombre"],
                "placa": args["placa"].upper(),
                "servicio": args["servicio"],
                "tipo_vehiculo": "moto",
            }
            event_id = booking.guardar_cita_estructurada(numero, datos, args["fecha"], args["hora"])
            if event_id:
                return f"Cita agendada correctamente para el {args['fecha']} a las {args['hora']}."
            return "No se pudo agendar automáticamente (error técnico). Dile al cliente con honestidad y ofrécele que un asesor lo va a contactar para confirmar manualmente."

        elif nombre_herramienta == "buscar_mis_citas":
            citas = google_calendar.buscar_eventos_por_cliente(numero)
            if not citas:
                return "El cliente no tiene citas próximas agendadas."
            lineas = [
                f"event_id={cita['id']} | {cita['resumen']} | {cita['inicio'].strftime('%Y-%m-%d %H:%M')}"
                for cita in citas
            ]
            return "Citas encontradas:\n" + "\n".join(lineas)

        elif nombre_herramienta == "cancelar_cita":
            exito = google_calendar.eliminar_evento(args["event_id"])
            return "Cita cancelada correctamente." if exito else "No se pudo cancelar automáticamente, avísale al cliente que un asesor lo va a ayudar."

        elif nombre_herramienta == "reagendar_cita":
            exito = google_calendar.actualizar_evento_estructurado(args["event_id"], args["fecha"], args["hora"])
            return "Cita reagendada correctamente." if exito else "No se pudo reagendar automáticamente, avísale al cliente que un asesor lo va a ayudar."

        elif nombre_herramienta == "enviar_pqr":
            if services_data.NUMERO_DUENO:
                send_text_message(services_data.NUMERO_DUENO, f"📩 *Nueva PQR*\nCliente: {numero}\nMensaje: {args['mensaje']}")
            return "PQR enviada al dueño del negocio."

        elif nombre_herramienta == "solicitar_asesor":
            if services_data.NUMERO_DUENO:
                send_text_message(services_data.NUMERO_DUENO, f"🙋 *Solicitud de asesor*\nEl cliente {numero} quiere hablar con una persona.")
            bot_control.pausar(numero)
            return "Aviso enviado al dueño. El bot se pausó automáticamente con este cliente por un rato."

        return "Herramienta no reconocida."

    except Exception as error:
        print(f"⚠️ Error ejecutando herramienta {nombre_herramienta}:", error)
        return "Ocurrió un error técnico ejecutando esta acción. Informa al cliente con honestidad y ofrece escalar con un asesor."


def handle_message(numero: str, texto: str):
    """Punto de entrada: procesa un mensaje de texto del cliente con Claude y responde por WhatsApp."""
    candado = _obtener_candado(numero)
    with candado:
        _procesar_mensaje(numero, texto)


def _procesar_mensaje(numero: str, texto: str):
    if numero not in historial_conversaciones:
        historial_conversaciones[numero] = []
    historial = historial_conversaciones[numero]

    historial.append({"role": "user", "content": texto})

    cliente = _get_cliente()
    system_prompt = _construir_system_prompt()

    try:
        respuesta = None
        while True:
            respuesta = cliente.messages.create(
                model=MODELO,
                max_tokens=1024,
                system=system_prompt,
                tools=HERRAMIENTAS,
                messages=historial,
            )
            historial.append({"role": "assistant", "content": respuesta.content})

            if respuesta.stop_reason != "tool_use":
                break

            resultados_herramientas = []
            for bloque in respuesta.content:
                if bloque.type == "tool_use":
                    resultado = _ejecutar_herramienta(bloque.name, bloque.input, numero)
                    resultados_herramientas.append({
                        "type": "tool_result",
                        "tool_use_id": bloque.id,
                        "content": resultado,
                    })
            historial.append({"role": "user", "content": resultados_herramientas})

        texto_respuesta = "".join(
            bloque.text for bloque in respuesta.content if bloque.type == "text"
        ).strip()

        if texto_respuesta:
            send_text_message(numero, texto_respuesta)

    except Exception as error:
        print("⚠️ Error al hablar con Claude:", error)
        send_text_message(numero, "Disculpa, tuve un problema técnico. ¿Puedes repetir tu mensaje? 🙏")

    finally:
        # Evita que el historial crezca sin límite con clientes que escriben mucho
        historial_conversaciones[numero] = historial[-MAX_MENSAJES_HISTORIAL:]
