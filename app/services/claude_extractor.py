import os
import json
import re
# pyrefly: ignore [missing-import]
from anthropic import Anthropic
import logging

logger = logging.getLogger(__name__)

class ClaudeFeatureExtractor:
    def __init__(self):
        self.api_key = os.getenv("CLAUDE_API_KEY")
        if self.api_key:
            self.client = Anthropic(api_key=self.api_key)
        else:
            self.client = None
        self.model = "claude-haiku-4-5-20251001"

    def extract_features(self, nombre_tramite: str, descripcion_politica: str, datos_dinamicos: dict) -> dict:
        if not self.client:
            logger.warning("No CLAUDE_API_KEY found, returning default features.")
            return self._default_features()

        system_prompt = (
            "Eres un analizador de datos crítico y avanzado. Tu misión principal es ESCUCHAR AL CLIENTE analizando a fondo "
            "los VALORES ESCRITOS EN 'Datos Dinámicos Cliente'. NO te dejes sesgar si el 'Nombre Trámite' suena aburrido o puramente administrativo. "
            "Si en los datos libres el cliente expresa quejas, fallas de sistema o exige inmediatez, debes darle peso a eso.\n\n"
            "Debes devolver ÚNICAMENTE un JSON puro, sin markdown, sin comillas invertidas y sin texto conversacional. "
            "El JSON debe tener exactamente estas 4 claves:\n"
            "- 'tema_principal' (String categórico: 'Tecnico', 'Financiero', 'Legal', 'Administrativo', 'Atencion_Cliente'. OJO: Si el cliente reporta fallas de acceso, caídas o errores de software en los campos libres, el tema DEBE SER 'Tecnico' sin importar el nombre del trámite)\n"
            "- 'tono_cliente' (String categórico: 'Calmado', 'Molesto', 'Emergencia', 'Neutro'. OJO: Si el cliente usa palabras como 'urgente', 'furioso', o reclama agresivamente, usa 'Emergencia' o 'Molesto')\n"
            "- 'menciona_fechas_limite' (Boolean: True si el cliente menciona plazos, fechas específicas u 'hoy mismo')\n"
            "- 'ruta_sugerida' (String: Sugiere en 3 a 5 palabras cómo debería ser atendido, ej. 'Ruta de Vía Rápida', 'Revisión por Especialista Técnica', 'Ruta Estándar')"
        )

        user_content = f"""
        Nombre Trámite: {nombre_tramite}
        Descripción Política: {descripcion_politica}
        Datos Dinámicos Cliente: {json.dumps(datos_dinamicos, ensure_ascii=False)}
        """

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_content}
                ]
            )
            raw_text = response.content[0].text
            return self._parse_json_robust(raw_text)
        except Exception as e:
            logger.error(f"Error calling Claude for feature extraction: {e}")
            return self._default_features()

    def _parse_json_robust(self, text: str) -> dict:
        try:
            # 1. Clean markdown code blocks
            text_cleaned = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL).strip()
            # 2. Extract JSON part if there is any conversational garbage
            match = re.search(r'\{.*\}', text_cleaned, flags=re.DOTALL)
            if match:
                text_cleaned = match.group(0)
            
            return json.loads(text_cleaned)
        except Exception as e:
            logger.error(f"JSON Parsing error. Raw text: {text}. Error: {e}")
            return self._default_features()

    def _default_features(self) -> dict:
        return {
            "tema_principal": "Administrativo",
            "tono_cliente": "Neutro",
            "menciona_fechas_limite": False,
            "ruta_sugerida": "Ruta Estándar"
        }
