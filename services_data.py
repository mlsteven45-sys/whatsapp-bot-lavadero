"""
Datos del negocio: nombre, horario, ubicación, servicios y precios.

Motobon es un negocio especializado únicamente en motos (no atiende carros).
Si en el futuro el negocio empieza a atender carros también, se puede agregar
una clave "carro" dentro de SERVICIOS, pero habría que volver a agregar el
paso de "tipo de vehículo" en conversation_manager.py.
"""

NOMBRE_NEGOCIO = "Motobon"

HORARIO_ATENCION = "Todos los días: 9:00 AM - 8:00 PM"

UBICACION = (
    "📍 Calle 80 #45-91, Campo Valdés, Aranjuez, Medellín, Antioquia\n"
    "Ver en mapa: https://www.google.com/maps/search/?api=1&query=Motobon+detailing+Cl.+80+%2345-91+Aranjuez+Medellin"
)

# Precios en pesos colombianos (COP).
SERVICIOS = {
    "moto": {
        "Lavado Detallado": 30000,
        "Lavado Premium": 35000,
        "Lavado Súper Premium": 90000,
        "Cerámico": 390000,
    },
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
