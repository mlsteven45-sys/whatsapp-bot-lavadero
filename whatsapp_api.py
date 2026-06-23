"""
Funciones para enviar mensajes a través de la API de WhatsApp Cloud (Meta).

Todas las funciones hacen una petición POST al endpoint /messages de la
Graph API de Meta, usando las credenciales guardadas en el archivo .env
(WHATSAPP_TOKEN y PHONE_NUMBER_ID).
"""
import os
import requests

GRAPH_API_VERSION = "v21.0"


def _credenciales():
    token = os.environ["WHATSAPP_TOKEN"]
    phone_number_id = os.environ["PHONE_NUMBER_ID"]
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    return url, headers


def _post(payload: dict):
    url, headers = _credenciales()
    respuesta = requests.post(url, headers=headers, json=payload, timeout=15)
    if respuesta.status_code >= 400:
        print("⚠️ Error al enviar mensaje:", respuesta.status_code, respuesta.text)
    return respuesta


def send_text_message(to: str, body: str):
    """Envía un mensaje de texto plano."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    return _post(payload)


def send_button_message(to: str, body: str, buttons: list):
    """
    Envía un mensaje con hasta 3 botones de respuesta rápida.
    buttons: lista de tuplas (id, titulo). Ej: [("si", "Sí"), ("no", "No")]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn_id, "title": titulo}}
                    for btn_id, titulo in buttons[:3]
                ]
            },
        },
    }
    return _post(payload)


def send_list_message(to: str, body: str, button_text: str, sections: list):
    """
    Envía un mensaje de lista desplegable (útil para menús con varias opciones).
    sections: lista de dicts, ej:
        [{"title": "Menú principal", "rows": [{"id": "x", "title": "Opción X"}]}]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text, "sections": sections},
        },
    }
    return _post(payload)
