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

    def _post_process_workflow(self, payload_str: str) -> str:
        """Normaliza la salida de la IA para asegurar consistencia de routing."""
        try:
            data = json.loads(payload_str)
            pasos = data.get("pasos", [])
            changed = False

            for paso in pasos:
                # Normalizar tipo: ACTIVITY, TASK, activity → ACTIVIDAD
                tipo = paso.get("tipo", "ACTIVIDAD")
                tipo_upper = tipo.upper().strip()
                if tipo_upper in ("ACTIVITY", "TASK"):
                    paso["tipo"] = "ACTIVIDAD"
                    changed = True
                elif tipo_upper in ("DECISION", "GATEWAY", "DECISIÓN"):
                    paso["tipo"] = "DECISION"
                    changed = True

                # Detectar ACTIVIDAD con múltiples rutas no-default → convertir a DECISION
                siguientes = paso.get("siguientes", {})
                if paso.get("tipo") == "ACTIVIDAD" and isinstance(siguientes, dict):
                    if len(siguientes) > 1 and "default" not in siguientes:
                        paso["tipo"] = "DECISION"
                        paso["formularioJson"] = None
                        changed = True

                # Asegurar que DECISION no tenga formularioJson
                if paso.get("tipo") == "DECISION" and paso.get("formularioJson") is not None:
                    paso["formularioJson"] = None
                    changed = True

            if changed:
                return json.dumps(data)
            return payload_str
        except Exception:
            return payload_str

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
        
        system_prompt = f"""SOLO JSON VÁLIDO. Sin markdown, sin explicaciones.

SCHEMA EXACTO:
{{"nombreTramite":"","descripcionTramite":"","categoria":"INTERNO|EXTERNO","costoBase":0,"formularioCliente":{{"type":"object","properties":{{}},"required":[]}},"pasos":[{{"id":"paso_N","tipo":"ACTIVIDAD|DECISION","departamentoId":"id|null","nombrePaso":"","formularioJson":{{}}|null,"siguientes":{{}}}}]}}

DEPARTAMENTOS DISPONIBLES: [{string_de_departamentos_bd}]

=== REGLAS CRÍTICAS DE ROUTING (SEGUIR AL PIE DE LA LETRA) ===

ACTIVIDAD (paso con formulario, un solo camino posible):
- SIEMPRE siguientes={{"default":"paso_N"}} para avanzar al siguiente paso
- SIEMPRE formularioJson con properties y required
- Si es el ÚLTIMO paso del trámite: siguientes={{}}
- NUNCA poner múltiples opciones como {{"Opcion1":"paso_X","Opcion2":"paso_Y"}} en ACTIVIDAD

DECISION (bifurcación, el usuario elige un camino):
- siguientes con nombres descriptivos: {{"Aprobado":"paso_X","Rechazado":"paso_Y"}}
- formularioJson SIEMPRE null (las decisiones no tienen formulario)
- Los nombres de las opciones deben ser legibles para humanos

ERROR COMÚN A EVITAR:
- SI un paso necesita que alguien elija entre opciones → DEBE ser DECISION, NO ACTIVIDAD
- Una ACTIVIDAD con siguientes={{"Disponible":"paso_3","No Disponible":"paso_4"}} está MAL → debe ser DECISION

CAMPO departamentoId:
- null = paso asignado al CLIENTE (lo responde desde la app móvil)
- "id_depto" = paso asignado a un FUNCIONARIO de ese departamento

TIPOS DE CAMPO EN formularioJson.properties:
- {{"type":"string"}} = texto libre
- {{"type":"number"}} = numérico
- {{"type":"boolean"}} = sí/no
- {{"type":"string","format":"date"}} = selector de fecha
- {{"type":"string","format":"date-time"}} = fecha y hora
- {{"type":"file"}} = archivo adjunto (PDF, imagen, etc)
- {{"type":"string","enum":["op1","op2"]}} = lista desplegable

FORMULARIO CLIENTE (formularioCliente):
- Datos que el cliente llena AL INICIAR el trámite. Mismos tipos de campo.

REGLAS:
1. INTERNO => costoBase=0
2. IDs secuenciales: paso_1, paso_2, paso_3...
3. NO crear bucles infinitos. Si un paso rechaza y pide corrección al cliente, debe tener un límite (máx 1 vuelta atrás).
4. Nombres y descripciones MUY concisos.
5. VALORES EXACTOS EN ESPAÑOL (NUNCA en inglés):
   - tipo: solo "ACTIVIDAD" o "DECISION" (NO "ACTIVITY", NO "DECISION_NODE", NO "TASK")
   - categoria: solo "INTERNO" o "EXTERNO" (NO "INTERNAL", NO "EXTERNAL")
"""
        workflow_budget = WORKFLOW_MAX_OUTPUT_TOKENS
        raw_response = await self._send_to_claude(system_prompt, politica_negocio, workflow_budget)
        
        normalized = self._normalize_json_object(raw_response)
        if normalized and self._is_valid_workflow_payload(normalized):
            return self._post_process_workflow(normalized)

        repair_budget = max(WORKFLOW_REPAIR_MIN_TOKENS, min(WORKFLOW_REPAIR_MAX_TOKENS, workflow_budget - 200))
        repaired = await self._intentar_reparar_workflow_json(raw_response, string_de_departamentos_bd, repair_budget)
        repaired_normalized = self._normalize_json_object(repaired)
        
        if repaired_normalized and self._is_valid_workflow_payload(repaired_normalized):
            return self._post_process_workflow(repaired_normalized)

        return self._build_fallback_workflow_json(politica_negocio, departamentos)

    async def asistir_editor_workflow(self, prompt: str, operator_role: str, mode: str, workflow_draft: Dict[str, Any], departamentos: List[DepartamentoInfo]) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("Debes enviar una consulta para el asistente.")

        departamentos_disponibles = ", ".join([f"{d.nombre} (ID: {d.id})" for d in departamentos])
        
        workflow_draft_json = json.dumps(workflow_draft) if workflow_draft else "{}"

        system_prompt = f"""SOLO JSON. Asiste operador en editor de workflows. Detecta inconsistencias, propone correcciones.
Deptos permitidos:[{departamentos_disponibles}].
VALORES EXACTOS EN ESPAÑOL (NUNCA inglés):
- tipo: solo "ACTIVIDAD" o "DECISION" (NO "ACTIVITY", NO "TASK")
- categoria: solo "INTERNO" o "EXTERNO" (NO "INTERNAL")

=== REGLAS CRÍTICAS DE ROUTING ===
ACTIVIDAD: siguientes SIEMPRE debe ser {{"default":"paso_N"}} o {{}} (fin).
- Si ves una ACTIVIDAD con múltiples rutas como {{"Opcion1":"paso_X","Opcion2":"paso_Y"}}, eso es un ERROR.
- Corrección: cambiar el tipo a DECISION y poner formularioJson=null.

DECISION: siguientes con nombres descriptivos {{"Aprobado":"paso_X","Rechazado":"paso_Y"}}.
- formularioJson DEBE ser null.
- Los nombres de las opciones son las etiquetas que verá el usuario.

VALIDACIONES:
- departamentoId null = Paso del CLIENTE. VÁLIDO.
- tipo DECISION = formularioJson DEBE ser null. CORRECTO.
- tipo ACTIVIDAD = formularioJson requerido con properties y required.
- ACTIVIDAD lineal: siguientes={{"default":"paso_N"}}. OBLIGATORIO.
- ACTIVIDAD final: siguientes={{}} (vacío = FIN del trámite).
- PROHIBIDO poner valores de datos como claves de siguientes.
- Tipos de campo válidos: string, number, boolean, file, string+format:date, string+format:date-time, string+enum.
- INTERNO => costoBase=0. No inventar IDs de departamentos.
- Bucles: máx 1 vuelta atrás permitida para correcciones.
Formato:{{\"respuesta\":\"texto breve\",\"guiaUso\":[],\"correccionesDetectadas\":[{{\"severidad\":\"ALTA|MEDIA|BAJA\",\"titulo\":\"\",\"detalle\":\"\",\"accion\":\"\"}}],\"workflowSugerido\":{{\"nombreTramite\":\"\",\"descripcionTramite\":\"\",\"categoria\":\"\",\"costoBase\":0,\"formularioCliente\":{{}},\"pasos\":[]}}|null}}
Sin cambios estructurales=workflowSugerido null. Sin markdown.
"""
        
        user_prompt = f"role:{operator_role or 'ADMIN'} mode:{mode or 'create'}\nWORKFLOW:{workflow_draft_json}\nCONSULTA:{prompt}"
        budget = 3000
        
        raw_response = await self._send_to_claude(system_prompt, user_prompt, budget)
        normalized = self._normalize_json_object(raw_response)
        
        if normalized:
            return normalized
            
# Fallback
        fallback = {
            "respuesta": "El asistente generó una estructura muy compleja y se interrumpió. Por favor, intenta ser más específico o pide cambios más pequeños.",
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
        system_prompt = """SOLO JSON. Autocompleta formulario desde texto del usuario.
Formato:{"sugerencia":{"campo":valor},"observacion":"texto corto"}
Solo campos existentes en properties del schema. Omite si faltan datos.
Tipos: string=texto, number=numérico, boolean=true/false, format:date=YYYY-MM-DD, format:date-time=YYYY-MM-DDTHH:mm:ss.
IGNORA campos tipo 'file' (son archivos, no autocompletables).
Enum=solo valores permitidos. Sin datos útiles=sugerencia vacía. Sin markdown.
"""
        user_prompt = f"modo={modo}\nSCHEMA:\n{schema_json}\n\nTEXTO_USUARIO:\n{texto_usuario}"
        budget = self._estimate_tokens_by_input_size(user_prompt, 500, 1000, 150)
        raw_response = await self._send_to_claude(system_prompt, user_prompt, budget)
        normalized = self._normalize_json_object(raw_response)
        return normalized if normalized else raw_response

    async def resumir_tramite(self, tramite_compacto: str) -> str:
        system_prompt = """SOLO JSON VÁLIDO. Genera resumen ejecutivo de trámite finalizado para el CLIENTE.
PROHIBIDO revelar: IDs internos, nombres de funcionarios, nombres de departamentos internos, datos sensibles.
Sé breve, claro y empático. Usa lenguaje simple orientado al ciudadano.

SCHEMA EXACTO (no añadir campos extra):
{"titulo":"nombre del trámite","estado":"Aprobado|Rechazado|Completado","resumen":"descripción breve de qué ocurrió en 2-3 oraciones","pasosClave":[{"nombre":"nombre del paso","resultado":"qué se determinó"}],"conclusion":"mensaje final para el cliente, próximos pasos si los hay"}

REGLAS:
- pasosClave: máximo 5 elementos, solo los más relevantes.
- No incluir pasos técnicos internos irrelevantes para el cliente.
- Si hubo rechazo, explicar el motivo de forma constructiva.
- conclusion debe ser un cierre amable y útil.
- Sin markdown, sin texto fuera del JSON."""

        budget = 800
        raw_response = await self._send_to_claude(system_prompt, tramite_compacto, budget)
        normalized = self._normalize_json_object(raw_response)

        if normalized:
            try:
                parsed = json.loads(normalized)
                required_keys = {"titulo", "estado", "resumen", "pasosClave", "conclusion"}
                if required_keys.issubset(parsed.keys()):
                    return normalized
            except:
                pass

        # Fallback
        fallback = {
            "titulo": "Resumen no disponible",
            "estado": "Completado",
            "resumen": "No fue posible generar un resumen detallado en este momento.",
            "pasosClave": [],
            "conclusion": "Su trámite ha sido procesado. Para más detalles, contacte a la institución."
        }
        return json.dumps(fallback)

