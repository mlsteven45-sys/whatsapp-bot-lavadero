"""
Base de datos simple de clientes: guarda el nombre de cada cliente
asociado a su número de WhatsApp en un archivo JSON (clientes.json).

Esto permite que el bot recuerde a los clientes que ya han escrito antes
y los salude por su nombre en conversaciones futuras.

El archivo clientes.json persiste en el servidor de Render entre
conversaciones normales. Solo se pierde si se hace un redespliegue
(igual que notificaciones_enviadas.json), pero como los nombres no
son datos críticos de operación, el impacto es mínimo — el bot
simplemente vuelve a preguntar el nombre la próxima vez.
"""
import json
import os

ARCHIVO_CLIENTES = os.path.join(os.path.dirname(__file__), "clientes.json")


def _leer_clientes() -> dict:
    if not os.path.exists(ARCHIVO_CLIENTES):
        return {}
    try:
        with open(ARCHIVO_CLIENTES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_clientes(data: dict):
    with open(ARCHIVO_CLIENTES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def obtener_nombre(numero: str) -> str | None:
    """Devuelve el nombre del cliente si ya lo conocemos, o None si es nuevo."""
    return _leer_clientes().get(numero)


def guardar_nombre(numero: str, nombre: str):
    """Guarda o actualiza el nombre de un cliente."""
    data = _leer_clientes()
    data[numero] = nombre.strip()
    _guardar_clientes(data)


def es_cliente_conocido(numero: str) -> bool:
    """True si ya tenemos el nombre de este cliente guardado."""
    return numero in _leer_clientes()
