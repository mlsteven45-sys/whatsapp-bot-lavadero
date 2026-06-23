"""
Webhook de Flask para el bot de WhatsApp del lavadero.

- GET  /webhook  -> verificación inicial que pide Meta al configurar el webhook
- POST /webhook  -> recibe cada mensaje nuevo que un cliente le envía al bot
"""
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import conversation_manager

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
        numero_cliente = mensaje["from"]
        tipo_mensaje = mensaje["type"]

        texto = None
        interactive_id = None

        if tipo_mensaje == "text":
            texto = mensaje["text"]["body"]
        elif tipo_mensaje == "interactive":
            interactive = mensaje["interactive"]
            if interactive["type"] == "button_reply":
                interactive_id = interactive["button_reply"]["id"]
            elif interactive["type"] == "list_reply":
                interactive_id = interactive["list_reply"]["id"]

        conversation_manager.handle_incoming_message(
            numero=numero_cliente,
            texto=texto,
            interactive_id=interactive_id,
        )

    except (KeyError, IndexError) as e:
        print("⚠️ No se pudo procesar el mensaje entrante:", e, data)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
