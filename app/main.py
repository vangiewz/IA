import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
from app.services.routing_engine import RoutingEngineService

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    RoutingEngineService().initialize_and_train()
    yield

app = FastAPI(
    title="Claude AI Workflow Microservice",
    description="Microservice for generating and assisting with workflows using Anthropic's Claude AI.",
    version="1.0.0",
    lifespan=lifespan
)

# Cargar variables de entorno (Local y Prod)
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
BACKEND_PROD_URL = os.getenv("BACKEND_PROD_URL", "https://tu-backend-prod.azurewebsites.net")

origins = [
    "http://localhost:8080",
    "http://localhost:4200",
    "https://frontend-workflow-kappa.vercel.app",
    BACKEND_PROD_URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/workflows/ai")

@app.get("/health")
def health_check():
    return {"status": "ok"}
