from pydantic import BaseModel
from typing import Optional, Dict, Any

class PredictPriorityRequest(BaseModel):
    tramiteId: str
    plantillaId: str
    nombrePlantilla: str
    descripcionPolitica: Optional[str] = None
    departamentoAsignado: Optional[str] = None
    cargaActualDepartamento: int = 0
    esViernesOFinSemana: bool = False
    datosCliente: Optional[Dict[str, Any]] = None

class PredictPriorityResponse(BaseModel):
    prioridad: str
    riesgoDemora: bool
    tiempoEstimadoDias: float = 0.0
    rutaSugerida: str = ""
    esAnomalo: bool = False
    features_usadas: Optional[Dict[str, Any]] = None

class RoutingFeedbackRequest(BaseModel):
    tema_principal: str
    tono_cliente: str
    menciona_fechas_limite: int
    departamento_asignado: str
    carga_actual_departamento: int
    es_viernes_o_fin_semana: int
    prioridad: str
    riesgo_demora: int
    tiempo_resolucion_dias: float
