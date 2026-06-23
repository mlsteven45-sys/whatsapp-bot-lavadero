"""
Máquina de estados de la conversación: controla en qué paso del menú
se encuentra cada cliente y decide qué responder.

Motobon solo atiende motos, por eso este flujo NO pregunta tipo de vehículo.

NOTA SOBRE EL ESTADO: se guarda en memoria (un diccionario de Python).
Se reinicia si el servidor se reinicia, pero esto NO afecta a cancelar o
reagendar citas: esa función busca directamente en Google Calendar usando
el número del cliente, no depende de este estado en memoria.
"""

import services_data
import booking
import google_calendar
from whatsapp_api import send_text_message, send_button_message, send_list_message, send_image_message

user_states = {}

# Palabras/frases que reinician el menú principal sin importar en qué parte
# de la conversación esté el cliente (siempre que no esté en medio de
# escribir un dato como su nombre, una fecha o una PQR).
SALUDOS_RESET = (
    "hola", "ola", "holaa", "menu", "menú", "inicio",
    "buenas", "buenas tardes", "buenas noches", "buenos dias", "buenos días",
    "buen dia", "buen día", "que tal", "qué tal", "hey", "buenas!", "saludos",
)


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
    entrada_normalizada = entrada.rstrip("!.,¡¿? ")

    # Estados donde NO queremos que un saludo interrumpa (el cliente está
    # escribiendo texto libre como su nombre, una fecha, o su PQR).
    estados_que_no_se_reinician = (
        "AGENDAR_NOMBRE", "AGENDAR_PLACA", "AGENDAR_FECHA", "AGENDAR_HORA",
        "REAGENDAR_FECHA", "REAGENDAR_HORA", "PQR_ESCRIBIENDO",
    )
    if entrada_normalizada in SALUDOS_RESET and estado_actual not in estados_que_no_se_reinician:
        return mostrar_menu_principal(numero)

    manejadores = {
        "INICIO": lambda: mostrar_menu_principal(numero),
        "MENU_PRINCIPAL": lambda: procesar_menu_principal(numero, entrada),
        "AGENDAR_SERVICIO": lambda: procesar_agendar_servicio(numero, entrada),
        "AGENDAR_NOMBRE": lambda: procesar_agendar_nombre(numero, texto),
        "AGENDAR_PLACA": lambda: procesar_agendar_placa(numero, texto),
        "AGENDAR_FECHA": lambda: procesar_agendar_fecha(numero, texto),
        "AGENDAR_HORA": lambda: procesar_agendar_hora(numero, texto),
        "AGENDAR_CONFIRMAR": lambda: procesar_agendar_confirmar(numero, entrada),
        "CANCELAR_SELECCIONAR": lambda: procesar_cancelar_seleccionar(numero, entrada),
        "CANCELAR_ACCION": lambda: procesar_cancelar_accion(numero, entrada),
        "REAGENDAR_FECHA": lambda: procesar_reagendar_fecha(numero, texto),
        "REAGENDAR_HORA": lambda: procesar_reagendar_hora(numero, texto),
        "REAGENDAR_CONFIRMAR": lambda: procesar_reagendar_confirmar(numero, entrada),
        "PQR_ESCRIBIENDO": lambda: procesar_pqr(numero, texto),
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
                {"id": "cancelar_reagendar", "title": "Cancelar o mover cita"},
                {"id": "pqr", "title": "PQR (quejas y reclamos)"},
                {"id": "horario", "title": "Horario de atención"},
                {"id": "ubicacion", "title": "Ubicación"},
                {"id": "asesor", "title": "Hablar con un asesor"},
            ],
        }],
    )


def procesar_menu_principal(numero: str, opcion: str):
    if opcion == "servicios":
        enviar_catalogo_servicios(numero)
        iniciar_agendamiento(numero)
    elif opcion == "agendar":
        iniciar_agendamiento(numero)
    elif opcion == "cancelar_reagendar":
        iniciar_cancelar_reagendar(numero)
    elif opcion == "pqr":
        iniciar_pqr(numero)
    elif opcion == "horario":
        send_text_message(numero, f"🕒 Horario de atención:\n{services_data.HORARIO_ATENCION}")
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "ubicacion":
        send_text_message(numero, services_data.UBICACION)
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "asesor":
        notificar_dueno_asesor(numero)
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
    set_estado(numero, "AGENDAR_NOMBRE")
    send_text_message(numero, "✍️ ¿Cuál es tu nombre completo?")


def procesar_agendar_nombre(numero: str, texto: str):
    if not texto or not texto.strip():
        send_text_message(numero, "Por favor escribe tu nombre completo.")
        return
    sesion = get_session(numero)
    sesion["datos"]["nombre"] = texto.strip()
    set_estado(numero, "AGENDAR_PLACA")
    send_text_message(numero, "🏍️ ¿Cuál es la placa de tu moto?")


def procesar_agendar_placa(numero: str, texto: str):
    if not texto or not texto.strip():
        send_text_message(numero, "Por favor escribe la placa de tu moto.")
        return
    sesion = get_session(numero)
    sesion["datos"]["placa"] = texto.strip().upper()
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
        f"Nombre: {datos['nombre']}\n"
        f"Placa: {datos['placa']}\n"
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


# ---------------- CANCELAR / REAGENDAR ----------------

def iniciar_cancelar_reagendar(numero: str):
    citas = google_calendar.buscar_eventos_por_cliente(numero)
    if not citas:
        send_text_message(numero, "No encontré citas próximas a tu número. Si crees que esto es un error, escribe *asesor*.")
        mostrar_menu_principal(numero, saludo=False)
        return

    sesion = get_session(numero)
    sesion["datos"]["citas_encontradas"] = citas

    filas = []
    for i, cita in enumerate(citas):
        fecha_legible = cita["inicio"].strftime("%d/%m/%Y %I:%M %p")
        filas.append({"id": f"cita_{i}", "title": fecha_legible, "description": cita["resumen"][:72]})

    set_estado(numero, "CANCELAR_SELECCIONAR")
    send_list_message(
        numero,
        body="Estas son tus próximas citas. ¿Cuál deseas cancelar o reagendar?",
        button_text="Ver citas",
        sections=[{"title": "Tus citas", "rows": filas}],
    )


def procesar_cancelar_seleccionar(numero: str, opcion: str):
    sesion = get_session(numero)
    citas = sesion["datos"].get("citas_encontradas", [])

    if not opcion.startswith("cita_"):
        send_text_message(numero, "Por favor selecciona una cita de la lista.")
        return

    try:
        indice = int(opcion.replace("cita_", ""))
        cita_elegida = citas[indice]
    except (ValueError, IndexError):
        send_text_message(numero, "No reconocí esa cita, intenta de nuevo.")
        return

    sesion["datos"]["cita_seleccionada"] = cita_elegida
    fecha_legible = cita_elegida["inicio"].strftime("%d/%m/%Y a las %I:%M %p")
    set_estado(numero, "CANCELAR_ACCION")
    send_button_message(
        numero,
        f"Cita seleccionada:\n{cita_elegida['resumen']}\n{fecha_legible}\n\n¿Qué deseas hacer?",
        buttons=[("cancelar_cita", "❌ Cancelar"), ("reagendar_cita", "📅 Reagendar")],
    )


def procesar_cancelar_accion(numero: str, opcion: str):
    sesion = get_session(numero)
    cita = sesion["datos"].get("cita_seleccionada")

    if opcion == "cancelar_cita":
        exito = google_calendar.eliminar_evento(cita["id"])
        if exito:
            send_text_message(numero, "✅ Tu cita fue cancelada correctamente.")
        else:
            send_text_message(numero, "⚠️ No pude cancelar la cita automáticamente. Por favor escribe *asesor* para que te ayudemos manualmente.")
        sesion["datos"] = {}
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "reagendar_cita":
        set_estado(numero, "REAGENDAR_FECHA")
        send_text_message(numero, "📅 ¿Para qué nueva fecha quieres mover la cita? (Ejemplo: 25/06/2026)")
    else:
        send_text_message(numero, "Por favor usa los botones para elegir una opción.")


def procesar_reagendar_fecha(numero: str, texto: str):
    if not texto:
        send_text_message(numero, "Por favor escribe una fecha válida (Ejemplo: 25/06/2026).")
        return
    sesion = get_session(numero)
    sesion["datos"]["nueva_fecha"] = texto.strip()
    set_estado(numero, "REAGENDAR_HORA")
    send_text_message(numero, "🕒 ¿A qué nueva hora? (Ejemplo: 3:00 PM)")


def procesar_reagendar_hora(numero: str, texto: str):
    if not texto:
        send_text_message(numero, "Por favor escribe una hora válida (Ejemplo: 3:00 PM).")
        return
    sesion = get_session(numero)
    sesion["datos"]["nueva_hora"] = texto.strip()
    datos = sesion["datos"]

    resumen = (
        "📋 *Nuevo horario propuesto:*\n"
        f"Fecha: {datos['nueva_fecha']}\n"
        f"Hora: {datos['nueva_hora']}\n\n"
        "¿Confirmas el cambio?"
    )
    set_estado(numero, "REAGENDAR_CONFIRMAR")
    send_button_message(numero, resumen, buttons=[("confirmar_reagendar", "✅ Confirmar"), ("cancelar_reagendar_cambio", "❌ Cancelar")])


def procesar_reagendar_confirmar(numero: str, opcion: str):
    sesion = get_session(numero)
    datos = sesion["datos"]
    cita = datos.get("cita_seleccionada")

    if opcion == "confirmar_reagendar":
        exito = google_calendar.actualizar_evento(cita["id"], datos["nueva_fecha"], datos["nueva_hora"])
        if exito:
            send_text_message(numero, "✅ ¡Listo! Tu cita fue reagendada.")
        else:
            send_text_message(numero, "⚠️ No pude actualizar la cita automáticamente. Por favor escribe *asesor* para que te ayudemos manualmente.")
        sesion["datos"] = {}
        mostrar_menu_principal(numero, saludo=False)
    elif opcion == "cancelar_reagendar_cambio":
        send_text_message(numero, "No se hicieron cambios en tu cita.")
        sesion["datos"] = {}
        mostrar_menu_principal(numero, saludo=False)
    else:
        send_text_message(numero, "Por favor usa los botones para confirmar o cancelar.")


# ---------------- PQR ----------------

def iniciar_pqr(numero: str):
    set_estado(numero, "PQR_ESCRIBIENDO")
    send_text_message(numero, "✍️ Cuéntanos tu petición, queja o reclamo y la haremos llegar directamente al equipo de Motobon.")


def procesar_pqr(numero: str, texto: str):
    if not texto or not texto.strip():
        send_text_message(numero, "Por favor escribe tu mensaje en texto.")
        return

    notificar_dueno_pqr(numero, texto.strip())
    send_text_message(numero, "✅ ¡Gracias! Tu mensaje fue enviado al equipo de Motobon, te contactaremos pronto.")
    mostrar_menu_principal(numero, saludo=False)


# ---------------- NOTIFICACIONES AL DUEÑO ----------------

def notificar_dueno_pqr(numero_cliente: str, mensaje: str):
    if not services_data.NUMERO_DUENO:
        print("⚠️ NUMERO_DUENO no configurado, no se pudo notificar la PQR.")
        return
    texto = f"📩 *Nueva PQR recibida*\nCliente: {numero_cliente}\nMensaje: {mensaje}"
    send_text_message(services_data.NUMERO_DUENO, texto)


def notificar_dueno_asesor(numero_cliente: str):
    if not services_data.NUMERO_DUENO:
        print("⚠️ NUMERO_DUENO no configurado, no se pudo notificar la solicitud de asesor.")
        return
    texto = f"🙋 *Solicitud de asesor*\nEl cliente {numero_cliente} quiere hablar con un asesor humano. Por favor contáctalo."
    send_text_message(services_data.NUMERO_DUENO, texto)
