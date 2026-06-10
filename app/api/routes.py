from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json

from app.models.schemas import ClaudePromptRequest, WorkflowAssistantRequest, ChatReportRequest
from app.services.claude_service import ClaudeAiService
from app.services.report_generator_service import ReportGeneratorService
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.post("/reports/chat")
async def process_report_chat(request: ChatReportRequest):
    try:
        service = ReportGeneratorService()
        result = await service.procesar_chat(request.historial)
        
        if result.get("estado") == "COMPLETO":
            # Return StreamingResponse with file
            return StreamingResponse(
                result["file_stream"],
                media_type=result["mime_type"],
                headers={
                    "Content-Disposition": f"attachment; filename={result['file_name']}",
                    "Access-Control-Expose-Headers": "Content-Disposition"
                }
            )
        else:
            # Return JSON
            return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

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

from app.models.schemas import LogsTramitesRequest, SugerirCamposRequest, ResumenTramiteRequest

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

@router.post("/summarize-tramite")
async def summarize_tramite(request: ResumenTramiteRequest):
    try:
        service = get_claude_service()
        json_output = await service.resumir_tramite(request.tramiteCompacto)
        try:
            return JSONResponse(content=json.loads(json_output))
        except:
            return JSONResponse(content={
                "titulo": "Resumen no disponible",
                "estado": "Completado",
                "resumen": "No fue posible generar el resumen.",
                "pasosClave": [],
                "conclusion": "Contacte a la institución para más detalles."
            })
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

from app.models.routing_schemas import PredictPriorityRequest
from app.services.routing_engine import RoutingEngineService
from app.services.claude_extractor import ClaudeFeatureExtractor

@router.post("/routing/predict-priority")
async def predict_priority(request: PredictPriorityRequest):
    try:
        # 1. Extraer features con Claude
        extractor = ClaudeFeatureExtractor()
        claude_features = extractor.extract_features(
            request.nombrePlantilla,
            request.descripcionPolitica or "",
            request.datosCliente or {}
        )
        
        # 2. Combinar features de Claude con los metadatos de Spring Boot
        features_to_predict = {
            "tema_principal": claude_features.get("tema_principal", "Administrativo"),
            "tono_cliente": claude_features.get("tono_cliente", "Neutro"),
            "menciona_fechas_limite": int(claude_features.get("menciona_fechas_limite", False)),
            "departamento_asignado": request.departamentoAsignado or "Desconocido",
            "carga_actual_departamento": request.cargaActualDepartamento,
            "es_viernes_o_fin_semana": int(request.esViernesOFinSemana)
        }
        
        # 3. Neural Network predict
        engine = RoutingEngineService()
        prediction = engine.predict_hybrid(features_to_predict)
        
        # --- EASTER EGG PARA LA DEFENSA ---
        # Si el usuario quiere forzar la aparición de un Alien en el Kanban para la demo:
        datos_str = json.dumps(request.datosCliente or {}).lower()
        if "fraude" in datos_str or "hacker" in datos_str or "anomalia" in datos_str:
            prediction["esAnomalo"] = True
            
        # 4. Combinar con rutaSugerida de LLM y features extraídas
        prediction["rutaSugerida"] = claude_features.get("ruta_sugerida", "Ruta Estándar")
        prediction["features_usadas"] = features_to_predict
        
        return JSONResponse(content=prediction)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

from app.models.routing_schemas import RoutingFeedbackRequest

@router.post("/routing/feedback")
async def routing_feedback(request: RoutingFeedbackRequest):
    try:
        engine = RoutingEngineService()
        real_data = {
            "tema_principal": request.tema_principal,
            "tono_cliente": request.tono_cliente,
            "menciona_fechas_limite": request.menciona_fechas_limite,
            "departamento_asignado": request.departamento_asignado,
            "carga_actual_departamento": request.carga_actual_departamento,
            "es_viernes_o_fin_semana": request.es_viernes_o_fin_semana,
            "prioridad": request.prioridad,
            "riesgo_demora": request.riesgo_demora,
            "tiempo_resolucion_dias": request.tiempo_resolucion_dias
        }
        success = engine.append_feedback_and_retrain(real_data)
        if success:
            return JSONResponse(content={"message": "Feedback recibido y modelo reentrenado."})
        else:
            return JSONResponse(status_code=500, content={"error": "Fallo al procesar feedback."})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

from app.api.chatbot_router import router as chatbot_router
router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
