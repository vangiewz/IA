from fastapi import APIRouter, HTTPException
from app.models.chatbot_schemas import ChatbotRequest, ChatbotResponse
from app.services.chatbot_service import ChatbotService

router = APIRouter()
chatbot_service = ChatbotService()

@router.post("/enrutar", response_model=ChatbotResponse)
def enrutar_chatbot(request: ChatbotRequest):
    try:
        return chatbot_service.enrutar_mensaje(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
