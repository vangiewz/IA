from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json

from app.models.schemas import ClaudePromptRequest, WorkflowAssistantRequest
from app.services.claude_service import ClaudeAiService

router = APIRouter()

def get_claude_service():
    return ClaudeAiService()

@router.post("/generate")
async def generate_workflow(request: ClaudePromptRequest):
    try:
        service = get_claude_service()
        json_output = await service.generar_workflow(request.politicaNegocio, request.departamentos)
        return JSONResponse(content=json.loads(json_output))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@router.post("/assist")
async def assist_workflow(request: WorkflowAssistantRequest):
    try:
        service = get_claude_service()
        json_output = await service.asistir_editor_workflow(
            request.prompt,
            request.operatorRole,
            request.mode,
            request.workflowDraft,
            request.departamentos
        )
        return JSONResponse(content=json.loads(json_output))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

from app.models.schemas import LogsTramitesRequest, SugerirCamposRequest

@router.post("/suggest-fields")
async def suggest_fields(request: SugerirCamposRequest):
    try:
        service = get_claude_service()
        json_output = await service.sugerir_campos_formulario(
            request.schemaJson,
            request.textoUsuario,
            request.modo
        )
        try:
            return JSONResponse(content=json.loads(json_output))
        except:
            return JSONResponse(content={"sugerencia": {}, "observacion": json_output})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@router.post("/analyze-logs")
async def analyze_logs(request: LogsTramitesRequest):
    try:
        service = get_claude_service()
        json_output = await service.analizar_logs_tramites(
            request.logsCompactosJson,
            request.horasEsperadasPromedio
        )
        try:
            return JSONResponse(content=json.loads(json_output))
        except:
            return JSONResponse(content={"insights": [], "planAccion": []})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
