"""
Máquina de estados de la conversación: controla en qué paso del menú
se encuentra cada cliente y decide qué responder según lo que escribe
o el botón/opción que selecciona.

Motobon solo atiende motos, por eso este flujo NO pregunta tipo de
vehículo (a diferencia de una versión genérica que atendería carro y moto).

NOTA SOBRE EL ESTADO: se guarda en memoria (un diccionario de Python).
Esto es suficiente para pruebas y para un volumen bajo de clientes, pero
se reinicia si el servidor se reinicia. Para producción con más tráfico,
lo ideal es guardar el estado en una base de datos (SQLite/PostgreSQL)
sin tener que cambiar la lógica de las funciones de abajo.
"""

import services_data
import booking
from whatsapp_api import send_text_message, send_button_message, send_list_message, send_image_message

# { "numero_whatsapp": {"estado": "...", "datos": {...}} }
user_states = {}


def get_session(numero: str) -> dict:
    if numero not in user_states:
        user_states[numero] = {"estado": "INICIO", "datos": {}}
    return user_states[numero]


def set_estado(numero: str, nuevo_estado: str):
    get_session(numero)["estado"] = nuevo_estado


def handle_incoming_message(numero: str, texto: str = None, interactive_id: str = None):
    """Punto de entrada principal, llamado desde app.py por cada mensaje recibido."""
    sesion = get_session(numero)
    estado_actual = sesion["estado"]
    entrada = (interactive_id or texto or "").strip().lower()

    # Atajo: "hola" o "menu" reinicia la conversación desde casi cualquier estado
    estados_que_no_se_reinician = ("AGENDAR_FECHA", "AGENDAR_HORA")
    if entrada in ("hola", "menu", "menú", "inicio") and estado_actual not in estados_que_no_se_reinician:
        return mostrar_menu_principal(numero)

    manejadores = {
        "INICIO": lambda: mostrar_menu_principal(numero),
        "MENU_PRINCIPAL": lambda: procesar_menu_principal(numero, entrada),
        "AGENDAR_SERVICIO": lambda: procesar_agendar_servicio(numero, entrada),
        "AGENDAR_FECHA": lambda: procesar_agendar_fecha(numero, texto),
        "AGENDAR_HORA": lambda: procesar_agendar_hora(numero, texto),
        "AGENDAR_CONFIRMAR": lambda: procesar_agendar_confirmar(numero, entrada),
    }

    manejador = manejadores.get(estado_actual, lambda: mostrar_menu_principal(numero))
    manejador()


# ---------------- MENÚ PRINCIPAL ----------------

def mostrar_menu_principal(numero: str, saludo: bool = True):
    set_estado(numero, "MENU_PRINCIPAL")
    if saludo:
        texto = f"👋 ¡Hola! Bienvenido a *{services_data.NOMBRE_NEGOCIO}*.\n¿En qué te puedo ayudar?"
    else:
        texto = "¿Hay algo más en lo que te pueda ayudar?"
    send_list_message(
        to=numero,
        body=texto,
        button_text="Ver opciones",
        sections=[{
            "title": "Menú principal",
            "rows": [
                {"id": "servicios", "title": "Servicios y precios"},
                {"id": "agendar", "title": "Agendar una cita"},
                {"id": "horario", "title": "Horario de atención"},
                {"id": "ubicacion", "title": "Ubicación"},
                {"id": "asesor", "title": "Hablar con un asesor"},
            ],
        }],
    )


def procesar_menu_principal(numero: str, opcion: str):
    if opcion == "servicios":
        enviar_catalogo_servicios(numero)
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "agendar":
        iniciar_agendamiento(numero)
    elif opcion == "horario":
        send_text_message(numero, f"🕒 Horario de atención:\n{services_data.HORARIO_ATENCION}")
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "ubicacion":
        send_text_message(numero, services_data.UBICACION)
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "asesor":
        send_text_message(numero, "👍 En un momento un asesor humano te va a contactar. ¡Gracias por tu paciencia!")
        set_estado(numero, "INICIO")
    else:
        send_text_message(numero, "No entendí esa opción 🙏 Por favor selecciona una de la lista.")
        mostrar_menu_principal(numero, saludo=False)


def enviar_catalogo_servicios(numero: str):
    """Envía una foto + precio por cada servicio disponible (o solo texto si no hay foto)."""
    send_text_message(numero, "🏍️ *Nuestros servicios:*")
    for nombre, precio in services_data.SERVICIOS["moto"].items():
        precio_formateado = f"{precio:,}".replace(",", ".")
        caption = f"{nombre}\n${precio_formateado} COP"
        url_imagen = services_data.url_imagen_servicio(nombre)
        if url_imagen:
            send_image_message(numero, url_imagen, caption=caption)
        else:
            send_text_message(numero, caption)


# ---------------- AGENDAMIENTO ----------------

def iniciar_agendamiento(numero: str):
    sesion = get_session(numero)
    sesion["datos"]["tipo_vehiculo"] = "moto"

    servicios_disponibles = list(services_data.SERVICIOS["moto"].keys())
    sesion["datos"]["servicios_disponibles"] = servicios_disponibles

    filas = [{"id": f"serv_{i}", "title": nombre} for i, nombre in enumerate(servicios_disponibles)]
    set_estado(numero, "AGENDAR_SERVICIO")
    send_list_message(
        numero,
        body="Vamos a agendar tu cita 📅\n¿Qué servicio deseas?",
        button_text="Ver servicios",
        sections=[{"title": "Servicios disponibles", "rows": filas}],
    )


def procesar_agendar_servicio(numero: str, opcion: str):
    sesion = get_session(numero)
    servicios_disponibles = sesion["datos"].get("servicios_disponibles", [])

    if not opcion.startswith("serv_"):
        send_text_message(numero, "Por favor selecciona un servicio de la lista.")
        return

    try:
        indice = int(opcion.replace("serv_", ""))
        servicio_elegido = servicios_disponibles[indice]
    except (ValueError, IndexError):
        send_text_message(numero, "No reconocí ese servicio, intenta de nuevo.")
        return

    sesion["datos"]["servicio"] = servicio_elegido
    set_estado(numero, "AGENDAR_FECHA")
    send_text_message(numero, "📅 ¿Para qué fecha quieres la cita? (Ejemplo: 25/06/2026)")


def procesar_agendar_fecha(numero: str, texto: str):
    if not texto:
        send_text_message(numero, "Por favor escribe una fecha válida (Ejemplo: 25/06/2026).")
        return
    sesion = get_session(numero)
    sesion["datos"]["fecha"] = texto.strip()
    set_estado(numero, "AGENDAR_HORA")
    send_text_message(numero, "🕒 ¿A qué hora te gustaría agendar? (Ejemplo: 3:00 PM)")


def procesar_agendar_hora(numero: str, texto: str):
    if not texto:
        send_text_message(numero, "Por favor escribe una hora válida (Ejemplo: 3:00 PM).")
        return

    sesion = get_session(numero)
    sesion["datos"]["hora"] = texto.strip()
    datos = sesion["datos"]

    resumen = (
        "📋 *Resumen de tu cita:*\n"
        f"Servicio: {datos['servicio']}\n"
        f"Fecha: {datos['fecha']}\n"
        f"Hora: {datos['hora']}\n\n"
        "¿Confirmas la cita?"
    )
    set_estado(numero, "AGENDAR_CONFIRMAR")
    send_button_message(numero, resumen, buttons=[("confirmar", "✅ Confirmar"), ("cancelar", "❌ Cancelar")])


def procesar_agendar_confirmar(numero: str, opcion: str):
    sesion = get_session(numero)
    datos = sesion["datos"]

    if opcion == "confirmar":
        booking.guardar_cita(numero, datos)
        send_text_message(numero, "✅ ¡Listo! Tu cita quedó agendada. Te esperamos 🏍️")
        sesion["datos"] = {}
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "cancelar":
        send_text_message(numero, "Cita cancelada. Si quieres empezar de nuevo, escribe *menu*.")
        sesion["datos"] = {}
        set_estado(numero, "INICIO")
    else:
        send_text_message(numero, "Por favor usa los botones para confirmar o cancelar.")
