"""
Datos del negocio: nombre, horario, ubicación, servicios y precios.

Motobon es un negocio especializado únicamente en motos (no atiende carros).
"""

NOMBRE_NEGOCIO = "Motobon"

HORARIO_ATENCION = "Todos los días: 9:00 AM - 8:00 PM"

UBICACION = (
    "📍 Calle 80 #45-91, Campo Valdés, Aranjuez, Medellín, Antioquia\n"
    "Ver en mapa: https://www.google.com/maps/search/?api=1&query=Motobon+detailing+Cl.+80+%2345-91+Aranjuez+Medellin"
)

# URL base donde está corriendo el bot en producción (Render).
# Si el dominio de Render cambia en el futuro, solo hay que actualizar esta línea.
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
# Para agregar/cambiar una foto: pon el archivo en la carpeta "static" del proyecto
# con este mismo nombre exacto, sube el cambio a GitHub, y Render se actualiza solo.
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
