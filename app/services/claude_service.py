import os
import json
import httpx
from typing import List, Dict, Any, Optional
from app.models.schemas import DepartamentoInfo

WORKFLOW_MIN_OUTPUT_TOKENS = 1500
WORKFLOW_MAX_OUTPUT_TOKENS = 2700
WORKFLOW_REPAIR_MIN_TOKENS = 1000
WORKFLOW_REPAIR_MAX_TOKENS = 2000

class ClaudeAiService:
    def __init__(self):
        self.api_key = os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY environment variable is not set")
        self.client = httpx.AsyncClient(timeout=60.0)

    def _estimate_tokens_by_input_size(self, text: str, min_tokens: int, max_tokens: int, overhead: int) -> int:
        length = len(text) if text else 0
        estimated_input_tokens = (length // 4) + overhead
        estimated_output = estimated_input_tokens

        if estimated_output < min_tokens:
            return min_tokens
        if estimated_output > max_tokens:
            return max_tokens
        return estimated_output

    def _estimate_workflow_output_tokens(self, politica_negocio: str) -> int:
        return self._estimate_tokens_by_input_size(
            politica_negocio,
            WORKFLOW_MIN_OUTPUT_TOKENS,
            WORKFLOW_MAX_OUTPUT_TOKENS,
            520
        )

    async def _send_to_claude(self, system_prompt: str, user_content: str, max_tokens: int) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_content}
            ]
        }

        response = await self.client.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            raise Exception(f"Error communicating with Claude AI: {response.text}")
            
        data = response.json()
        if "content" in data and len(data["content"]) > 0:
            return data["content"][0].get("text", "")
            
        raise Exception("Error communicating with Claude AI: No content in response")

    def _normalize_json_object(self, raw: str) -> Optional[str]:
        if not raw or not raw.strip():
            return None
            
        trimmed = raw.strip()
        if trimmed.startswith("```"):
            lines = trimmed.split('\n')
            if lines[0].startswith("```"):
                lines.pop(0)
            if lines and lines[-1].startswith("```"):
                lines.pop()
            trimmed = '\n'.join(lines).strip()

        start = trimmed.find('{')
        if start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False

        for i in range(start, len(trimmed)):
            c = trimmed[i]

            if escaped:
                escaped = False
                continue

            if c == '\\':
                escaped = True
                continue

            if c == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return trimmed[start:i+1]

        return None

    def _is_valid_workflow_payload(self, payload: str) -> bool:
        try:
            node = json.loads(payload)
            if not isinstance(node, dict):
                return False
            if "nombreTramite" not in node or "descripcionTramite" not in node:
                return False
            if "categoria" not in node or "costoBase" not in node:
                return False
            if "formularioCliente" not in node:
                return False
            pasos = node.get("pasos")
            if not isinstance(pasos, list):
                return False
            return True
        except Exception:
            return False

    async def _intentar_reparar_workflow_json(self, raw_response: str, departamentos_disponibles: str, max_tokens: int) -> str:
        system_prompt = f"""
SOLO JSON valido compacto. Repara workflow truncado/malformado. Campos requeridos:nombreTramite,descripcionTramite,categoria,costoBase,formularioCliente,pasos[]. Deptos:[{departamentos_disponibles}]. Completa coherente si truncado. Sin description ni markdown.
"""
        user_prompt = "REPARAR:\n" + raw_response
        return await self._send_to_claude(system_prompt, user_prompt, max_tokens)

    def _build_fallback_workflow_json(self, politica_negocio: str, departamentos: List[DepartamentoInfo]) -> str:
        depto_id = departamentos[0].id if departamentos else None

        formulario_cliente = {
            "type": "object",
            "properties": {
                "detalleSolicitud": {"type": "string"},
                "fechaSolicitud": {"type": "string", "format": "date"}
            },
            "required": ["detalleSolicitud", "fechaSolicitud"]
        }

        pasos = [
            {
                "id": "paso_1",
                "tipo": "ACTIVIDAD",
                "departamentoId": depto_id,
                "nombrePaso": "Revision Inicial",
                "formularioJson": {
                    "type": "object",
                    "properties": {"datosCompletos": {"type": "boolean"}},
                    "required": ["datosCompletos"]
                },
                "siguientes": {"default": "paso_2"}
            },
            {
                "id": "paso_2",
                "tipo": "DECISION",
                "departamentoId": depto_id,
                "nombrePaso": "Datos Correctos",
                "formularioJson": None,
                "siguientes": {"Aprobado": "paso_3", "Rechazado": "paso_4"}
            },
            {
                "id": "paso_3",
                "tipo": "ACTIVIDAD",
                "departamentoId": depto_id,
                "nombrePaso": "Resolucion Final",
                "formularioJson": {
                    "type": "object",
                    "properties": {"resultado": {"type": "string"}},
                    "required": ["resultado"]
                },
                "siguientes": {}
            },
            {
                "id": "paso_4",
                "tipo": "ACTIVIDAD",
                "departamentoId": None,
                "nombrePaso": "Solicitud de Ajustes",
                "formularioJson": {
                    "type": "object",
                    "properties": {"observacionCliente": {"type": "string"}},
                    "required": ["observacionCliente"]
                },
                "siguientes": {"default": "paso_1"}
            }
        ]

        nombre = "Workflow Generado"
        if politica_negocio and politica_negocio.strip():
            stripped = politica_negocio.strip()
            nombre = stripped[:50] if len(stripped) > 50 else stripped

        payload = {
            "nombreTramite": nombre,
            "descripcionTramite": "Flujo generado por fallback automatico.",
            "categoria": "EXTERNO",
            "costoBase": 0,
            "formularioCliente": formulario_cliente,
            "pasos": pasos
        }

        return json.dumps(payload)

    async def generar_workflow(self, politica_negocio: str, departamentos: List[DepartamentoInfo]) -> str:
        string_de_departamentos_bd = ", ".join([f"{d.nombre} (ID: {d.id})" for d in departamentos])
        
        system_prompt = f"""
ACTÚA COMO API. DEVUELVE ÚNICAMENTE JSON VÁLIDO. CERO COMENTARIOS.
Estructura estricta:{{"nombreTramite":"","descripcionTramite":"","categoria":"INTERNO|EXTERNO","costoBase":0,"formularioCliente":{{"type":"object","properties":{{}},"required":[]}},"pasos":[{{"id":"paso_N","tipo":"ACTIVIDAD|DECISION","departamentoId":"id|null","nombrePaso":"","formularioJson":{{}}|null,"siguientes":{{}}}}]}}
Deptos:[{string_de_departamentos_bd}]. 
REGLAS: 
1. Cliente = departamentoId null. 
2. DECISION = formularioJson null, siguientes por condicion (ej. "Aprobado":"paso_3"). 
3. ACTIVIDAD = formularioJson requerido, siguientes:"default" si lineal.
4. INTERNO => costoBase=0.
5. Formularios soportan tipos: string, number, boolean, date. Agrega campos obligatorios a "required": [].
6. SÉ EXTREMADAMENTE CONCISO. Descripciones y nombres muy cortos. Minimiza tokens. Evita bucles infinitos.
"""
        workflow_budget = self._estimate_workflow_output_tokens(politica_negocio)
        raw_response = await self._send_to_claude(system_prompt, politica_negocio, workflow_budget)
        
        normalized = self._normalize_json_object(raw_response)
        if normalized and self._is_valid_workflow_payload(normalized):
            return normalized

        repair_budget = max(WORKFLOW_REPAIR_MIN_TOKENS, min(WORKFLOW_REPAIR_MAX_TOKENS, workflow_budget - 200))
        repaired = await self._intentar_reparar_workflow_json(raw_response, string_de_departamentos_bd, repair_budget)
        repaired_normalized = self._normalize_json_object(repaired)
        
        if repaired_normalized and self._is_valid_workflow_payload(repaired_normalized):
            return repaired_normalized

        return self._build_fallback_workflow_json(politica_negocio, departamentos)

    async def asistir_editor_workflow(self, prompt: str, operator_role: str, mode: str, workflow_draft: Dict[str, Any], departamentos: List[DepartamentoInfo]) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("Debes enviar una consulta para el asistente.")

        departamentos_disponibles = ", ".join([f"{d.nombre} (ID: {d.id})" for d in departamentos])
        
        workflow_draft_json = json.dumps(workflow_draft) if workflow_draft else "{}"

        system_prompt = f"""
SOLO JSON. Asiste operador en editor de workflows. Detecta inconsistencias, propone correcciones.
Deptos permitidos:[{departamentos_disponibles}]. 
REGLAS ESTRICTAS (NO MARQUES COMO ERROR LO SIGUIENTE):
- departamentoId nulo = Paso del CLIENTE. Esto es VÁLIDO Y CORRECTO.
- tipo DECISION = formularioJson debe ser null. Las decisiones NO llevan formulario. Esto es CORRECTO.
- tipo ACTIVIDAD = formularioJson requerido, siguientes="default" si es lineal.
- INTERNO => costoBase=0. No inventar IDs.
Formato:{{"respuesta":"texto breve","guiaUso":[],"correccionesDetectadas":[{{"severidad":"ALTA|MEDIA|BAJA","titulo":"","detalle":"","accion":""}}],"workflowSugerido":{{"nombreTramite":"","descripcionTramite":"","categoria":"","costoBase":0,"formularioCliente":{{}},"pasos":[]}}|null}}
Sin cambios estructurales=workflowSugerido null. Sin markdown.
"""
        
        user_prompt = f"role:{operator_role or 'ADMIN'} mode:{mode or 'create'}\nWORKFLOW:{workflow_draft_json}\nCONSULTA:{prompt}"
        budget = self._estimate_tokens_by_input_size(user_prompt, 900, 1800, 250)
        
        raw_response = await self._send_to_claude(system_prompt, user_prompt, budget)
        normalized = self._normalize_json_object(raw_response)
        
        if normalized:
            return normalized
            
        # Fallback
        fallback = {
            "respuesta": raw_response[:500] + "..." if len(raw_response) > 500 else raw_response,
            "guiaUso": [],
            "correccionesDetectadas": [],
            "workflowSugerido": None
        }
        return json.dumps(fallback)

    async def analizar_logs_tramites(self, logs_compactos_json: str, horas_esperadas_promedio: float) -> str:
        system_prompt = """
SOLO JSON. Analiza logs de tiempos de tramites. Identifica deptos que superen promedio, sugiere causa(FALTA_PERSONAL|COMPLEJIDAD_FORMULARIO|MIXTO), plan de accion.
departamentoId="CLIENTE"=tiempo externo, no retraso interno. Severidad: CRITICO>=24h, ADVERTENCIA>=8h<24h, INFO=resto.
Schema:{"insights":[{"severidad":"","titulo":"","descripcion":"","departamentoId":null,"funcionarioId":null,"retrasoHoras":0,"causaProbable":""}],"planAccion":[{"prioridad":"ALTA|MEDIA|BAJA","accion":"","objetivo":"","plazoHoras":""}]}
Usa horasEsperadasPromedio como referencia. Sin markdown.
"""
        user_prompt = f"horasEsperadasPromedio={horas_esperadas_promedio}\n{logs_compactos_json}"
        budget = self._estimate_tokens_by_input_size(user_prompt, 900, 1700, 300)
        raw_response = await self._send_to_claude(system_prompt, user_prompt, budget)
        normalized = self._normalize_json_object(raw_response)
        return normalized if normalized else raw_response

    async def sugerir_campos_formulario(self, schema_json: str, texto_usuario: str, modo: str) -> str:
        system_prompt = """
SOLO JSON. Autocompleta formulario desde texto del usuario.
Formato:{"sugerencia":{"campo":valor},"observacion":"texto corto"}
Solo campos existentes en properties del schema. Omite si faltan datos. Respeta tipos(string,number,boolean,date). Enum=solo valores permitidos. Sin datos utiles=sugerencia vacia. Sin markdown.
"""
        user_prompt = f"modo={modo}\nSCHEMA:\n{schema_json}\n\nTEXTO_USUARIO:\n{texto_usuario}"
        budget = self._estimate_tokens_by_input_size(user_prompt, 500, 1000, 150)
        raw_response = await self._send_to_claude(system_prompt, user_prompt, budget)
        normalized = self._normalize_json_object(raw_response)
        return normalized if normalized else raw_response

