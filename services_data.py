"""
Datos del negocio: nombre, horario, ubicación, servicios y precios.

Motobon es un negocio especializado únicamente en motos (no atiende carros).
"""

NOMBRE_NEGOCIO = "Motobon"

HORARIO_ATENCION = "Todos los días: 9:00 AM - 8:00 PM (Incluye domingos y festivos)"

UBICACION = (
    "📍 Calle 80 #45-91, Campo Valdés, Aranjuez, Medellín, Antioquia\n"
    "Ver en mapa: https://www.google.com/maps/search/?api=1&query=Motobon+detailing+Cl.+80+%2345-91+Aranjuez+Medellin"
)

# Número de WhatsApp PERSONAL del dueño, donde recibe avisos de "asesor" y PQR.
# Formato: código de país + número, sin "+", sin espacios. Ej: "573001234567"
# Si se deja vacío (""), el bot simplemente no envía esas notificaciones.
NUMERO_DUENO = "573015747945"

# URL base donde está corriendo el bot en producción (Render).
BASE_URL = "https://motobot-7iig.onrender.com"

# Precios en pesos colombianos (COP).
SERVICIOS = {
    "moto": {
        "Lavado Detallado": 30000,
        "Lavado Premium": 35000,
        "Lavado Súper Premium": 90000,
        "Cerámico": 390000,
    },
}

# Nombre del archivo de imagen (dentro de la carpeta /static) para cada servicio.
IMAGENES_SERVICIOS = {
    "Lavado Detallado": "lavado_detallado.jpeg",
    "Lavado Premium": "lavado_premium.jpeg",
    "Lavado Súper Premium": "lavado_super_premium.jpeg",
    "Cerámico": "ceramico.jpeg",
}


def formatear_precios(tipo_vehiculo: str = "moto") -> str:
    """Devuelve un texto con la lista de servicios y precios."""
    servicios = SERVICIOS.get(tipo_vehiculo, {})
    if not servicios:
        return "No encontré servicios disponibles."

    lineas = []
    for nombre, precio in servicios.items():
        precio_formateado = f"{precio:,}".replace(",", ".")
        lineas.append(f"• {nombre}: ${precio_formateado} COP")
    return "\n".join(lineas)


def url_imagen_servicio(nombre_servicio: str) -> str | None:
    """Devuelve la URL pública completa de la imagen de un servicio, o None si no tiene."""
    archivo = IMAGENES_SERVICIOS.get(nombre_servicio)
    if not archivo:
        return None
    return f"{BASE_URL}/static/{archivo}"
