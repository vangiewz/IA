import os
import json
from anthropic import Anthropic
from app.models.chatbot_schemas import ChatbotRequest, ChatbotResponse

class ChatbotService:
    def __init__(self):
        # Usar la misma clave que ya se usa en la aplicación
        self.api_key = os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            raise Exception("CLAUDE_API_KEY no está configurada")
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-haiku-4-5-20251001"

    def enrutar_mensaje(self, request: ChatbotRequest) -> ChatbotResponse:
        system_prompt = f"""
        Eres un asistente clasificador de trámites inteligente.
        Tu único propósito es analizar el mensaje del usuario y buscar si coincide con alguno de los trámites disponibles en el catálogo.

        Catálogo de trámites disponibles:
        {request.catalogoTramites}

        Instrucciones ESTRICTAS:
        1. Analiza la intención del usuario.
        2. Si la intención coincide claramente con un trámite del catálogo, devuelve el ID del trámite (como string) y un mensaje amigable invitando a iniciar el trámite.
        3. Si la intención NO coincide con NINGÚN trámite del catálogo, devuelve tramiteId nulo (null) y un mensaje indicando que no puedes ayudar con eso, ofreciendo los trámites disponibles.
        4. TU RESPUESTA DEBE SER ÚNICA Y EXCLUSIVAMENTE UN JSON VÁLIDO. No agregues texto antes ni después del JSON. No uses bloques de código Markdown (```json ... ```), solo el texto en JSON puro.

        Formato esperado exacto:
        {{
            "tramiteId": "id-del-tramite-o-null",
            "mensaje": "Tu respuesta al usuario"
        }}
        """

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": request.mensajeUsuario}
                ],
                temperature=0.0
            )
            
            respuesta_texto = response.content[0].text.strip()
            
            # Intentar limpiar si la IA devuelve markdown a pesar de la instrucción
            if respuesta_texto.startswith("```json"):
                respuesta_texto = respuesta_texto[7:]
            if respuesta_texto.endswith("```"):
                respuesta_texto = respuesta_texto[:-3]
            
            respuesta_texto = respuesta_texto.strip()
            
            data = json.loads(respuesta_texto)
            return ChatbotResponse(
                tramiteId=data.get("tramiteId"),
                mensaje=data.get("mensaje", "No pude procesar tu solicitud.")
            )
        except json.JSONDecodeError as e:
            # Fallback en caso de que Claude no respete el JSON
            return ChatbotResponse(
                tramiteId=None,
                mensaje="Hubo un error al interpretar mi respuesta interna. Por favor, intenta de nuevo. (Error: No-JSON)"
            )
        except Exception as e:
            return ChatbotResponse(
                tramiteId=None,
                mensaje=f"Error interno del servidor AI: {str(e)}"
            )
