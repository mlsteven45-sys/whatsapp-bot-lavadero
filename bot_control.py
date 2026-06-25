"""
Control manual del bot por parte del dueño: permite pausar o reanudar las
respuestas automáticas para un cliente específico — por ejemplo, cuando el
dueño decide atender personalmente una conversación (después de un "asesor"
o por su propia decisión).

El dueño controla esto enviando comandos de texto al MISMO número del bot,
desde su WhatsApp personal (el número en services_data.NUMERO_DUENO):

    pausar 573001112233        -> pausa a ese cliente por 60 minutos (por defecto)
    pausar 573001112233 30     -> pausa a ese cliente por 30 minutos
    reanudar 573001112233      -> reanuda de inmediato

Mientras un cliente está "pausado", el bot no le responde nada — se asume
que el dueño lo está atendiendo personalmente por fuera (llamada, WhatsApp
personal, o la app de WhatsApp Business si más adelante se activa
Coexistencia).
"""
from datetime import datetime, timedelta

MINUTOS_PAUSA_POR_DEFECTO = 60

_pausas = {}  # { "numero_cliente": datetime_hasta_cuando (UTC) }


def esta_pausado(numero_cliente: str) -> bool:
    """True si el bot debe quedarse callado con este cliente en este momento."""
    vence = _pausas.get(numero_cliente)
    if vence is None:
        return False
    if datetime.utcnow() >= vence:
        del _pausas[numero_cliente]  # ya venció, lo limpiamos solo
        return False
    return True


def pausar(numero_cliente: str, minutos: int = MINUTOS_PAUSA_POR_DEFECTO):
    _pausas[numero_cliente] = datetime.utcnow() + timedelta(minutes=minutos)


def reanudar(numero_cliente: str):
    _pausas.pop(numero_cliente, None)


def procesar_comando_dueno(texto: str) -> str:
    """
    Interpreta un mensaje del dueño como un comando de control y lo ejecuta.
    Devuelve el texto de respuesta que se le debe enviar al dueño.
    """
    partes = texto.strip().split()
    if not partes:
        return _texto_ayuda()

    comando = partes[0].lower()

    if comando == "pausar" and len(partes) >= 2:
        numero_cliente = partes[1]
        minutos = MINUTOS_PAUSA_POR_DEFECTO
        if len(partes) >= 3 and partes[2].isdigit():
            minutos = int(partes[2])
        pausar(numero_cliente, minutos)
        return f"🔇 Listo, el bot dejó de responderle a {numero_cliente} por {minutos} minutos."

    if comando == "reanudar" and len(partes) >= 2:
        numero_cliente = partes[1]
        reanudar(numero_cliente)
        return f"🔊 Listo, el bot volvió a responderle a {numero_cliente} con normalidad."

    return _texto_ayuda()


def _texto_ayuda() -> str:
    return (
        "🤖 *Comandos disponibles:*\n"
        "_pausar <número>_ — el bot deja de responderle a ese cliente por 60 min\n"
        "_pausar <número> <minutos>_ — pausa por un tiempo específico\n"
        "_reanudar <número>_ — el bot vuelve a responderle normal\n\n"
        "Ejemplo: pausar 573001112233 30"
    )
