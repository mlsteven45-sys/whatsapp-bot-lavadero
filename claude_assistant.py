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
import time

import anthropic

import services_data
import booking
import google_calendar
import cliente_db
from whatsapp_api import send_text_message, send_image_message

MODELO = "claude-haiku-4-5"
MAX_MENSAJES_HISTORIAL = 20  # cuántos mensajes recientes recordamos por cliente

historial_conversaciones = {}  # { "numero": [ {"role":..., "content":...}, ... ] }
ultima_actividad = {}          # { "numero": timestamp_utc }
retoma_enviada = {}            # { "numero": True } — para enviar el recordatorio solo 1 vez

MINUTOS_INACTIVIDAD_RETOMA = 15  # minutos sin respuesta para enviar recordatorio

# Estados que indican que el cliente está en medio de un agendamiento incompleto
ESTADOS_AGENDAMIENTO = {
    "AGENDAR_SERVICIO", "AGENDAR_NOMBRE", "AGENDAR_PLACA",
    "AGENDAR_FECHA", "AGENDAR_HORA", "AGENDAR_CONFIRMAR"
}

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


def _construir_system_prompt(numero: str = "") -> str:
    # Construir el catálogo detallado con descripción, precio y tiempo por servicio
    catalogo = []
    for nombre, precio in services_data.SERVICIOS["moto"].items():
        precio_fmt = (f"${precio:,}".replace(",", ".") + " COP" if precio is not None else "Según cotización")
        descripcion = services_data.DESCRIPCIONES_SERVICIOS.get(nombre, "")
        catalogo.append(f"• *{nombre}* — {precio_fmt}\n  {descripcion}")
    catalogo_texto = "\n\n".join(catalogo)

    # Personalización: si ya conocemos al cliente, dáselo a Claude
    nombre_cliente = cliente_db.obtener_nombre(numero) if numero else None
    if nombre_cliente:
        contexto_cliente = (
            f"\nCLIENTE ACTUAL: Ya conoces a este cliente, su nombre es *{nombre_cliente}*. "
            f"Salúdalo por su nombre de forma natural al inicio de la conversación."
        )
    else:
        contexto_cliente = (
            "\nCLIENTE ACTUAL: No tenemos el nombre de este cliente aún. "
            "No lo pidas de entrada — espera a que la conversación llegue a un punto natural "
            "(como cuando quiera agendar una cita)."
        )

    return f"""Eres el asistente virtual de {services_data.NOMBRE_NEGOCIO}, un negocio de lavado y detallado de motos en Medellín, Colombia. Hablas por WhatsApp directamente con los clientes.

INFORMACIÓN DEL NEGOCIO:
- Horario de atención: {services_data.HORARIO_ATENCION}
- Ubicación: {services_data.UBICACION}
- Métodos de pago: {services_data.METODOS_PAGO}

DIFERENCIAS ENTRE SERVICIOS (úsala cuando el cliente pregunte qué diferencia hay entre ellos):
{services_data.DIFERENCIAS_SERVICIOS}

SERVICIOS (con descripción detallada, precio y tiempo estimado):
{catalogo_texto}

CAPACIDAD:
- Máximo {services_data.MAX_CITAS_POR_HORA} motos por franja horaria de 1 hora.
- Antes de confirmar una cita, SIEMPRE usa la herramienta verificar_disponibilidad para consultar si hay cupo disponible en la fecha y hora solicitadas.
- Si no hay cupo, infórmale al cliente de forma amable y sugiérele otra hora.

FECHA DE HOY: {_fecha_actual_bogota()}

CÓMO DEBES COMPORTARTE:
- Habla como una persona real, cálida y persuasiva, en español colombiano natural y cercano. No suenes robótico ni distante.
- Usa emojis con naturalidad, como lo haría alguien joven y dinámico en WhatsApp.
- Respuestas cortas y directas, como en una conversación real de WhatsApp. Nada de párrafos largos.
- Cuando el cliente dude o posponga, sé persuasivo pero sin presionar: usa frases como "súper, te esperamos por acá 🍀", "cuando quieras aquí estamos 🏍️", o similares — cálidas y que inviten a volver.
- Si el cliente pregunta por la ubicación o cómo llegar, usa EXACTAMENTE esta referencia: "Si te ubicas en el sector, buscas la estación Manrique del Metro Plus y bajas tan solo una cuadrita hasta el semáforo 🚦 ¡Inmediatamente nos verás!"
- Nunca des por perdido a un cliente que duda — siempre cierra con algo positivo que lo invite a regresar.
- Si el cliente dice que queda lejos o que Motobon le queda difícil: convéncelo de forma natural mencionando que estamos a solo 15 minutos del centro de Medellín, que contamos con una zona de espera cómoda con televisor y agua mientras su moto queda lista, y que el viaje vale totalmente la pena por la calidad del servicio. Cierra invitándolo a agendar. Ejemplo de tono: "¡No te preocupes! Estamos a tan solo 15 minutos del centro de Medellín 🏍️ Y mientras tu moto queda impecable, puedes esperar aquí con nosotros — tenemos zona de espera con televisor y agua. ¡Vale la pena el viaje, te lo garantizamos! ¿Te animamos a agendar?" — adáptalo según el contexto pero siempre mencionando los 15 min y la zona de espera.
- Si el cliente pregunta cómo llegar o pide un punto de referencia, usa EXACTAMENTE esto: "Si te ubicas en el sector, buscas la estación Manrique del Metro Plus y bajas tan solo una cuadrita hasta el semáforo 🚦 ¡Inmediatamente nos verás!" 
- Si preguntan por un servicio específico, responde con la descripción detallada, el precio y el tiempo estimado.
- Si preguntan por métodos de pago, responde directamente con la información de arriba.
- Si el cliente parece interesado en ver los servicios visualmente, ofrece mostrarle fotos con la herramienta mostrar_fotos_servicios.
- Para agendar una cita necesitas 4 cosas: nombre completo, placa de la moto, servicio deseado, fecha y hora. Pregúntalos de forma natural. Antes de llamar a agendar_cita, repite el resumen y espera que el cliente confirme explícitamente.
- Las fechas/horas que le pases a las herramientas deben ir en formato fecha="YYYY-MM-DD" y hora="HH:MM" en 24 horas. Tú interpretas lo que diga el cliente (ej: "el viernes a las 3pm") usando la fecha de hoy como referencia.
- Si el cliente responde confirmando su asistencia a una cita (ej: "sí confirmo", "ahí estaré", "confirmo"), respóndele con entusiasmo y usa notificar_confirmacion para avisarle al dueño que ese cliente confirmó.
- NUNCA ofrezcas proactivamente la opción de cancelar ni la menciones como sugerencia. Solo procesa la cancelación si el cliente EXPLÍCITAMENTE dice que quiere cancelar (ej: "quiero cancelar mi cita", "cancela la reserva").
- Si el cliente tiene una queja, reclamo o petición (PQR), usa enviar_pqr con su mensaje.
- Si el cliente pide EXPLÍCITAMENTE hablar con una persona/asesor humano, usa solicitar_asesor y luego responde EXACTAMENTE con este texto: "Listo, ya le avisamos al dueño que quieres hablar con nosotros directamente 👋 Alguien de nuestro equipo te escribirá en poco tiempo para ayudarte con lo que necesites. ¿Necesitas algo más?"
- Si el cliente pregunta por el servicio PPF (Paint Protection Film), explícale los beneficios y dile que el precio es según cotización — usa solicitar_asesor para que un asesor lo contacte y le cotice. Resérvala solo para cuando el cliente la pida de verdad, no para cuando tú no sepas un detalle.
- Si simplemente no sabes un detalle puntual, sé honesto y sigue ayudando con normalidad.
- REGLA IMPORTANTE: nunca le digas al cliente que algo ya se hizo sin haber llamado realmente a la herramienta correspondiente primero.
- Cuando envíes fotos u otro contenido al cliente, NO agregues frases de confirmación innecesarias como "Ya están ahí", "Listo, ya las envié" o similares antes de hacer una pregunta de seguimiento. Ve directo a la pregunta o comentario siguiente.
- PROMOCIÓN ACTIVA: Si el cliente escribe exactamente o algo muy similar a "¡Hola! Quiero más información." (mensaje que llega de pauta de Instagram/Facebook), respóndele con el saludo normal y usa EXACTAMENTE este texto para la promoción: "¡Hola! 👋 Bienvenido a Motobon. Tenemos una promoción especial activa que está muy buena — incluye full lavada con shampoo de pH neutro, full desengrasado, restauración de partes negras plásticas con producto premium, desmanchada, polichado y brillada de toda la moto. Normalmente tiene un valor de $90.000, pero por tiempo limitado está en solo $60.000. ¿Deseas aprovechar la promoción y agendar? 🏍️" No menciones otros servicios en ese primer mensaje.
- Nunca inventes información que no tengas. Si no sabes algo, dilo con honestidad.{contexto_cliente}"""


HERRAMIENTAS = [
    {
        "name": "verificar_disponibilidad",
        "description": "Verifica si hay cupo disponible en una fecha y hora específica (máximo 2 motos por hora). Úsala SIEMPRE antes de agendar_cita.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                "hora": {"type": "string", "description": "Hora en formato 24h HH:MM"},
            },
            "required": ["fecha", "hora"],
        },
    },
    {
        "name": "mostrar_fotos_servicios",
        "description": "Envía al cliente fotos de los servicios disponibles con sus precios. Úsala cuando el cliente quiera ver cómo se ven los servicios.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mostrar_fotos_referencia",
        "description": "Envía fotos de trabajos realizados como referencia general. Úsala cuando el cliente pida ver referencias, trabajos anteriores, resultados o ejemplos del trabajo de Motobon.",
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
        "name": "notificar_confirmacion",
        "description": "Notifica al dueño que un cliente confirmó su asistencia a la cita. Úsala cuando el cliente responda afirmativamente al recordatorio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_cliente": {"type": "string", "description": "Nombre del cliente que confirmó"},
            },
            "required": ["nombre_cliente"],
        },
    },
    {
        "name": "buscar_mis_citas",
        "description": "Busca las próximas citas agendadas de este cliente. Úsala cuando el cliente quiera ver, reagendar o cancelar una cita.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancelar_cita",
        "description": "Cancela una cita existente, identificada por su event_id (obtenido con buscar_mis_citas). Solo úsala si el cliente EXPLÍCITAMENTE pidió cancelar.",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "reagendar_cita",
        "description": "Cambia la fecha/hora de una cita existente, identificada por su event_id (obtenido con buscar_mis_citas).",
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
        if nombre_herramienta == "mostrar_fotos_referencia":
            for archivo in services_data.FOTOS_REFERENCIA:
                url = f"{services_data.BASE_URL}/static/{archivo}"
                send_image_message(numero, url)
            return "Fotos de referencia enviadas al cliente."

        elif nombre_herramienta == "verificar_disponibilidad":
            cantidad = google_calendar.contar_citas_en_franja(args["fecha"], args["hora"])
            disponibles = services_data.MAX_CITAS_POR_HORA - cantidad
            if disponibles > 0:
                return f"Hay cupo disponible para esa hora ({disponibles} de {services_data.MAX_CITAS_POR_HORA} espacios libres). Puedes proceder a agendar."
            return f"No hay cupo disponible para esa hora (ya hay {cantidad} motos agendadas y el máximo es {services_data.MAX_CITAS_POR_HORA}). Sugiere al cliente otra hora."

        elif nombre_herramienta == "notificar_confirmacion":
            if services_data.NUMERO_DUENO:
                send_text_message(
                    services_data.NUMERO_DUENO,
                    f"✅ *Confirmación de cita*\n{args.get('nombre_cliente', 'Un cliente')} confirmó su asistencia. Ya está listo para su servicio 🏍️"
                )
            return "Confirmación enviada al dueño."

        elif nombre_herramienta == "mostrar_fotos_servicios":
            for nombre_serv, precio in services_data.SERVICIOS["moto"].items():
                precio_fmt = (f"{precio:,}".replace(",", ".") if precio is not None else "Según cotización")
                url_imagen = services_data.url_imagen_servicio(nombre_serv)
                if url_imagen:
                    send_image_message(numero, url_imagen, caption=f"{nombre_serv}\n${precio_fmt} COP")
            return "Fotos enviadas correctamente al cliente."

        elif nombre_herramienta == "agendar_cita":
            # PPF no se agenda en Calendar — derivar al asesor
            if "PPF" in args.get("servicio", ""):
                if services_data.NUMERO_DUENO:
                    send_text_message(services_data.NUMERO_DUENO,
                        f"🛡️ *Solicitud de PPF*\nCliente: {numero}\nNombre: {args.get('nombre', 'No indicado')}\nPlaca: {args.get('placa', 'No indicada')}")
                return "El PPF requiere cotización personalizada. Avisa al cliente que un asesor lo va a contactar para darle el precio y coordinar la cita."

            datos = {
                "nombre": args["nombre"],
                "placa": args["placa"].upper(),
                "servicio": args["servicio"],
                "tipo_vehiculo": "moto",
            }
            event_id = booking.guardar_cita_estructurada(numero, datos, args["fecha"], args["hora"])

            # Notificar al dueño con todos los detalles de la cita
            if services_data.NUMERO_DUENO and event_id:
                from datetime import datetime
                try:
                    fecha_legible = datetime.strptime(args["fecha"], "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    fecha_legible = args["fecha"]
                hora_dt = args["hora"]
                try:
                    hora_legible = datetime.strptime(args["hora"], "%H:%M").strftime("%I:%M %p").lstrip("0")
                except Exception:
                    hora_legible = args["hora"]

                precio = services_data.SERVICIOS.get("moto", {}).get(args["servicio"])
                if precio is not None:
                    precio_texto = (f"${precio:,}".replace(",", ".") + " COP" if precio is not None else "Según cotización")
                else:
                    precio_texto = "Según cotización"

                mensaje_dueno = (
                    f"📅 *Nueva cita agendada*\n\n"
                    f"👤 *Nombre:* {args['nombre']}\n"
                    f"🏍️ *Placa:* {args['placa'].upper()}\n"
                    f"🔧 *Servicio:* {args['servicio']}\n"
                    f"💰 *Precio:* {precio_texto}\n"
                    f"📆 *Fecha:* {fecha_legible}\n"
                    f"🕒 *Hora:* {hora_legible}\n"
                    f"📱 *WhatsApp cliente:* {numero}"
                )
                send_text_message(services_data.NUMERO_DUENO, mensaje_dueno)

            # Guardar el nombre del cliente para futuras conversaciones
            if args.get("nombre"):
                cliente_db.guardar_nombre(numero, args["nombre"])

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
            event_id = args["event_id"]
            fecha = args["fecha"]
            hora = args["hora"]
            print(f"🔄 Reagendando evento: event_id={event_id}, fecha={fecha}, hora={hora}")
            exito = google_calendar.actualizar_evento_estructurado(event_id, fecha, hora)
            print(f"🔄 Resultado reagendar: {exito}")
            return "Cita reagendada correctamente." if exito else "No se pudo reagendar automáticamente, avísale al cliente que un asesor lo va a ayudar."

        elif nombre_herramienta == "enviar_pqr":
            if services_data.NUMERO_DUENO:
                send_text_message(services_data.NUMERO_DUENO, f"📩 *Nueva PQR*\nCliente: {numero}\nMensaje: {args['mensaje']}")
            return "PQR enviada al dueño del negocio."

        elif nombre_herramienta == "solicitar_asesor":
            print(f"🔔 Ejecutando solicitar_asesor — NUMERO_DUENO={services_data.NUMERO_DUENO}", flush=True)
            if services_data.NUMERO_DUENO:
                try:
                    resp = send_text_message(services_data.NUMERO_DUENO, f"🙋 *Solicitud de asesor*\nEl cliente {numero} quiere hablar con una persona.")
                    print(f"🔔 Resultado envío al asesor: {resp.status_code} {resp.text[:100]}", flush=True)
                except Exception as ex:
                    print(f"🔔 Error enviando al asesor: {ex}", flush=True)
            else:
                print("🔔 NUMERO_DUENO está vacío!", flush=True)
            return "Aviso enviado al dueño. El bot sigue funcionando normal con este cliente a menos que el dueño decida pausarlo manualmente."

        return "Herramienta no reconocida."

    except Exception as error:
        print(f"⚠️ Error ejecutando herramienta {nombre_herramienta}:", error)
        return "Ocurrió un error técnico ejecutando esta acción. Informa al cliente con honestidad y ofrece escalar con un asesor."


def verificar_retomas():
    """
    Revisa si hay clientes inactivos en medio de un agendamiento
    y les envía UN mensaje de retoma. Se llama desde el scheduler cada 5 minutos.
    """
    ahora = datetime.utcnow()
    limite = timedelta(minutes=MINUTOS_INACTIVIDAD_RETOMA)

    for numero, ts in list(ultima_actividad.items()):
        if retoma_enviada.get(numero):
            continue  # Ya le enviamos el recordatorio, no repetir

        if ahora - ts < limite:
            continue  # Aún no han pasado 15 minutos

        # Verificar si está en medio de un agendamiento
        sesion = historial_conversaciones.get(numero, [])
        if not sesion:
            continue

        # Buscar el último mensaje del asistente para ver si quedó esperando datos
        ultimo_assistant = next(
            (m for m in reversed(sesion) if m.get("role") == "assistant"),
            None
        )
        if not ultimo_assistant:
            continue

        # Enviar recordatorio de retoma
        try:
            send_text_message(
                numero,
                "¡Hola! 👋 Veo que quedamos a medias con tu agendamiento. "
                "¿Seguimos? Aquí estamos para ayudarte 🏍️"
            )
            retoma_enviada[numero] = True
            print(f"✅ Retoma enviada a {numero}")
        except Exception as e:
            print(f"⚠️ Error enviando retoma a {numero}: {e}")


def handle_message(numero: str, texto: str):
    """Punto de entrada: procesa un mensaje de texto del cliente con Claude y responde por WhatsApp."""
    candado = _obtener_candado(numero)
    with candado:
        _procesar_mensaje(numero, texto)


def _procesar_mensaje(numero: str, texto: str):
    # Actualizar timestamp de última actividad
    ultima_actividad[numero] = datetime.utcnow()
    # Si el cliente retomó, limpiar el flag de retoma enviada
    retoma_enviada.pop(numero, None)

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
                print(f"🤖 Claude respondió sin herramienta (stop_reason={respuesta.stop_reason})", flush=True)
                break

            resultados_herramientas = []
            for bloque in respuesta.content:
                if bloque.type == "tool_use":
                    print(f"🔧 Claude usa herramienta: {bloque.name} con args: {bloque.input}", flush=True)
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
