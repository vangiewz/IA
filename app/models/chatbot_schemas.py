from pydantic import BaseModel
from typing import Optional

class ChatbotRequest(BaseModel):
    mensajeUsuario: str
    catalogoTramites: str

class ChatbotResponse(BaseModel):
    tramiteId: Optional[str] = None
    mensaje: str
