"""
Webhook de Flask para el bot de WhatsApp de Motobon.

El bot entiende lenguaje natural usando la API de Claude (ver
claude_assistant.py) en vez de un menú de opciones fijas con botones.

IMPORTANTE: el procesamiento con Claude (y las herramientas que pueda usar,
como Google Calendar) puede tardar varios segundos. Si no respondemos a
Meta de inmediato, Meta puede reintentar el envío del mismo mensaje varias
veces, causando respuestas duplicadas o confusas. Por eso el procesamiento
real se hace en un hilo en segundo plano (threading), y esta ruta responde
"200 OK" a Meta de inmediato, sin esperar a que Claude termine.

- GET  /webhook  -> verificación inicial que pide Meta
- POST /webhook  -> recibe cada mensaje nuevo y lo procesa con Claude (async)
"""
import os
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import claude_assistant
import bot_control
import services_data
from whatsapp_api import send_text_message

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")


@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    """Meta llama a esta ruta una sola vez para confirmar que el webhook es válido."""
    modo = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if modo == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Token de verificación inválido", 403


@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    """Meta envía aquí cada mensaje nuevo que un cliente le escribe al bot."""
    data = request.get_json()

    try:
        entry = data["entry"][0]
        cambio = entry["changes"][0]["value"]

        if "messages" not in cambio:
            # Puede ser una notificación de estado (entregado/leído); la ignoramos
            return jsonify({"status": "ok"}), 200

        mensaje = cambio["messages"][0]
        numero_remitente = mensaje["from"]
        tipo_mensaje = mensaje["type"]

        if tipo_mensaje != "text":
            send_text_message(
                numero_remitente,
                "Por ahora solo puedo leer mensajes de texto 🙏 ¿Me cuentas en palabras qué necesitas?",
            )
            return jsonify({"status": "ok"}), 200

        texto = mensaje["text"]["body"]

        # Si quien escribe es el dueño, tratamos su mensaje como un COMANDO
        # de control (pausar/reanudar), no como una conversación con Claude.
        if services_data.NUMERO_DUENO and numero_remitente == services_data.NUMERO_DUENO:
            respuesta = bot_control.procesar_comando_dueno(texto)
            send_text_message(numero_remitente, respuesta)
            return jsonify({"status": "ok"}), 200

        # Si este cliente está pausado (el dueño lo está atendiendo
        # personalmente), el bot se queda en silencio.
        if bot_control.esta_pausado(numero_remitente):
            return jsonify({"status": "ok"}), 200

        # Procesamos en segundo plano: así respondemos a Meta YA, sin
        # esperar a que Claude (y sus herramientas) terminen de trabajar.
        hilo = threading.Thread(
            target=claude_assistant.handle_message,
            args=(numero_remitente, texto),
            daemon=True,
        )
        hilo.start()

    except (KeyError, IndexError) as e:
        print("⚠️ No se pudo procesar el mensaje entrante:", e, data)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
