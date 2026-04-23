from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class DepartamentoInfo(BaseModel):
    id: str
    nombre: str

class ClaudePromptRequest(BaseModel):
    politicaNegocio: str
    departamentos: List[DepartamentoInfo] = []

class WorkflowAssistantRequest(BaseModel):
    prompt: str
    operatorRole: Optional[str] = "ADMIN"
    mode: Optional[str] = "create"
    workflowDraft: Optional[Dict[str, Any]] = None
    departamentos: List[DepartamentoInfo] = []

class LogsTramitesRequest(BaseModel):
    logsCompactosJson: str
    horasEsperadasPromedio: float

class SugerirCamposRequest(BaseModel):
    schemaJson: str
    textoUsuario: str
    modo: str
