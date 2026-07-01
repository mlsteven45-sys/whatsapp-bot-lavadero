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

DIFERENCIAS_SERVICIOS = """
*¿Cuál es la diferencia entre los servicios?*

🔹 *Detallado vs Premium:*
Ambos incluyen lavado completo, desengrasado total e hidratación de partes negras. La diferencia clave es que el *Lavado Premium* incorpora una etapa adicional de restauración de partes negras y un *brillado a mano con cera protectora Meguiar's profesional*, que le da un acabado con mayor profundidad de brillo y protección a la pintura. El *Detallado* no incluye esta etapa de brillado.

🔹 *Premium vs Súper Premium:*
El *Lavado Súper Premium* va un paso más allá: en lugar del brillado a mano con cera, se realiza un *pulido y brillado con máquina profesional*, lo que permite corregir microrayones superficiales, eliminar manchas más profundas y descontaminar la pintura a un nivel que la cera convencional no alcanza. Además incluye desmanchado y descontaminación química de la pintura. El resultado es un acabado más uniforme y duradero.
"""

METODOS_PAGO = "Contamos con pago en efectivo, transferencia bancaria y para servicios Súper Premium crédito con Wompi."

# Número de WhatsApp PERSONAL del dueño, donde recibe avisos de "asesor" y PQR.
NUMERO_DUENO = "573015747945"

# URL base donde está corriendo el bot en producción (Render).
BASE_URL = "https://motobot-7iig.onrender.com"

# Máximo de citas permitidas por franja horaria de 1 hora
MAX_CITAS_POR_HORA = 2

# Precios en pesos colombianos (COP).
SERVICIOS = {
    "moto": {
        "Lavado Detallado": 30000,
        "Lavado Premium": 35000,
        "Lavado Súper Premium": 90000,
        "Cerámico": 390000,
    },
}

# Descripción técnica y detallada de cada servicio.
DESCRIPCIONES_SERVICIOS = {
    "Lavado Detallado": (
        "Lavado completo con shampoo de pH neutro, desengrasado total de la moto "
        "(incluyendo kit de arrastre) e hidratación de partes negras. "
        "Tiempo aproximado: 2 horas."
    ),
    "Lavado Premium": (
        "Lavado completo con shampoo de pH neutro, desengrasado total (incluyendo kit de arrastre), "
        "hidratación y restauración de partes negras, y brillado a mano con cera protectora "
        "Meguiar's profesional. "
        "Tiempo aproximado: 2 horas."
    ),
    "Lavado Súper Premium": (
        "Lavado profundo con shampoo de pH neutro, desengrasado profundo (incluyendo kit de arrastre), "
        "restauración de partes negras con producto premium, desmanchado y descontaminación de la pintura, "
        "pulido y brillado con máquina profesional. "
        "Tiempo aproximado: 2 horas."
    ),
    "Cerámico": (
        "Lavado profundo con shampoo profesional de pH neutro, desengrasado completo de toda la moto "
        "(incluyendo kit de arrastre), restauración de partes negras con producto premium, "
        "preparación de la pintura para la aplicación del recubrimiento cerámico, "
        "detallado completo con desmanchado total, descontaminación de la pintura, "
        "eliminación de microrayones e imperfecciones y finalmente aplicación del recubrimiento cerámico. "
        "Tiempo aproximado: 2 días."
    ),
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
