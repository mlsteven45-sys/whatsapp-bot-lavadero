# Bot de WhatsApp para Lavadero de Carros y Motos

Bot que responde automáticamente por WhatsApp: muestra servicios y precios,
informa horario y ubicación, y permite agendar citas paso a paso usando
menús de botones y listas (no texto libre).

## Estructura del proyecto

```
app.py                  -> Webhook de Flask (recibe y verifica mensajes)
conversation_manager.py -> Máquina de estados: controla el flujo del menú
whatsapp_api.py          -> Funciones para enviar mensajes vía Graph API de Meta
services_data.py         -> Servicios, precios, horario y ubicación (EDITA AQUÍ)
booking.py                -> Guarda las citas en citas.json
requirements.txt          -> Dependencias de Python
.env.example               -> Plantilla de variables de entorno
```

## 1. Instalación

```bash
# Crear y activar un entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate      # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

## 2. Configurar credenciales

1. Copia `.env.example` y renómbralo a `.env`
2. Rellena los 4 valores con los datos que obtuviste en el panel de Meta
   (Paso 1. Pruébalo → Configuración de la API):
   - `WHATSAPP_TOKEN`: el token de acceso que generaste
   - `PHONE_NUMBER_ID`
   - `WHATSAPP_BUSINESS_ACCOUNT_ID`
   - `VERIFY_TOKEN`: inventa cualquier palabra secreta (la vas a necesitar
     en el paso 4)

## 3. Personalizar la información del negocio

Abre `services_data.py` y reemplaza:
- `NOMBRE_NEGOCIO`
- `HORARIO_ATENCION`
- `UBICACION`
- Los precios dentro de `SERVICIOS` (carro y moto)

No necesitas tocar ningún otro archivo para hacer estos cambios.

## 4. Correr el bot localmente

```bash
python app.py
```

Debería decir algo como `Running on http://0.0.0.0:5000`.

## 5. Exponer el bot a internet con ngrok (para pruebas)

Mientras el bot corre localmente, en otra terminal:

```bash
ngrok http 5000
```

Ngrok te va a dar una URL pública tipo `https://algo-random.ngrok-free.app`.
Esa es la URL que vas a usar en el paso 6.

## 6. Configurar el webhook en el panel de Meta

1. Ve a tu app en developers.facebook.com → WhatsApp → Configuración → Webhooks
2. URL de retorno de llamada (Callback URL): `https://tu-url-de-ngrok.app/webhook`
3. Verify Token: el mismo valor que pusiste en `VERIFY_TOKEN` dentro de `.env`
4. Haz clic en "Verificar y guardar"
5. Suscríbete al campo `messages` (Webhook fields)

Si todo está bien, Meta te debería confirmar que el webhook quedó verificado.

## 7. Probar el bot

Escríbele al número de WhatsApp de prueba desde tu celular. Deberías recibir
el menú principal con las opciones (Servicios, Agendar cita, Horario,
Ubicación, Hablar con un asesor).

## Notas importantes antes de pasar a producción

- El token temporal de Meta expira en 24 horas. Para producción, crea un
  **token permanente** con un System User en Business Settings.
- El estado de la conversación se guarda en memoria (se borra si el
  servidor se reinicia). Para más volumen de clientes, conviene pasar a
  una base de datos (SQLite o PostgreSQL).
- `ngrok` es solo para pruebas. Para producción real, despliega `app.py`
  en un servicio con HTTPS permanente como Render o Railway, y apunta el
  webhook de Meta a esa URL final.
