import logging
from tenacity import retry, wait_fixed, stop_after_attempt, before_log, after_log

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
from src.models.corrida_model import Corrida, CorridaInDB
from src.database.mongo_client import MongoClientSingleton, get_mongo_collection
from src.database.redis_client import get_redis_client
import redis
from contextlib import asynccontextmanager
import os, pathlib
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
from src.producer import broker  # Importa o broker compartilhado
from bson import ObjectId

# Carrega as variáveis de ambiente do arquivo .env (se existir) e do sistema
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    MongoClientSingleton().connect()
    await broker.start()

    try:
        redis_client = get_redis_client()
        # Set initial balances only if they don't exist
        redis_client.hsetnx("motorista:carla", "saldo", 100)
        redis_client.hsetnx("motorista:joao", "saldo", 200)
        print("Redis initialized and initial driver balances set if needed.")
    except redis.exceptions.ConnectionError as e:
        print(f"Failed to connect to Redis during startup: {e}")
    
    yield
    
    # Shutdown
    await broker.close()
    MongoClientSingleton().close()

app = FastAPI(
    title="TransFlow API",
    description="API para gerenciamento de corridas de transporte.",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check():
    """
    Verifica a saúde das conexões com o banco de dados e o cache.
    """
    mongo_status = "down"
    redis_status = "down"

    # Check MongoDB connection
    try:
        mongo_client = MongoClientSingleton().client
        mongo_client.admin.command('ping')
        mongo_status = "ok"
    except PyMongoError as e:
        print(f"MongoDB health check failed: {e}")

    # Check Redis connection
    try:
        redis_client = get_redis_client()
        if redis_client.ping():
            redis_status = "ok"
    except redis.exceptions.ConnectionError as e:
        print(f"Redis health check failed: {e}")

    if mongo_status == "down" or redis_status == "down":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"mongodb": mongo_status, "redis": redis_status}
        )

    return {"mongodb": mongo_status, "redis": redis_status}

@app.get("/saldo/{motorista}", status_code=status.HTTP_200_OK, tags=["Saldo"])
async def get_saldo(motorista: str):
    """
    Retorna o saldo atual de um motorista.
    """
    try:
        redis_client = get_redis_client()
        chave_motorista = f"motorista:{motorista}"
        saldo = redis_client.hget(chave_motorista, "saldo")
        if saldo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Motorista não encontrado ou sem saldo."
            )
        return {"nome_motorista": motorista, "saldo": float(saldo)}
    except redis.exceptions.ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis connection error: {e}"
        )

# Define a retryable publish function
@retry(
    wait=wait_fixed(2),  # Wait 2 seconds between retries
    stop=stop_after_attempt(3),  # Try 3 times
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARNING),
    reraise=True # Re-raise the exception after all retries fail
)
async def publish_message_with_retries(data: dict):
    await broker.publish(data, queue="corridas_queue")

@app.post("/corridas", status_code=status.HTTP_202_ACCEPTED, tags=["Corridas"])
async def create_corrida(corrida: Corrida):
    """
    Publica um evento 'corrida_finalizada' para processamento assíncrono.
    """
    try:
        corrida_dict = corrida.model_dump()
        await publish_message_with_retries(corrida_dict)
        return {"status": "Corrida recebida e sendo processada."}
    except Exception as e:
        logger.error(f"Falha persistente ao publicar evento da corrida após múltiplas tentativas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao publicar evento da corrida após tentativas: {e}"
        )


@app.get("/corridas", response_model=List[CorridaInDB], tags=["Corridas"])
async def list_corridas():
    """
    Lista todas as corridas cadastradas no sistema.
    """
    try:
        corridas_collection = get_mongo_collection()
        corridas = []
        for corrida in corridas_collection.find():
            doc = dict(corrida)
            raw_id = doc.get("_id")
            doc["id_corrida"] = str(raw_id)
            if isinstance(raw_id, ObjectId):
                doc["_id"] = raw_id
            else:
                try:
                    if ObjectId.is_valid(str(raw_id)):
                        doc["_id"] = ObjectId(str(raw_id))
                    else:
                        doc.pop("_id", None)
                except Exception:
                    doc.pop("_id", None)
            corridas.append(CorridaInDB(**doc))
        return corridas
    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )

@app.get("/corridas/{forma_pagamento}", response_model=List[CorridaInDB], tags=["Corridas"])
async def filter_corridas_by_payment(forma_pagamento: str):
    """
    Filtra corridas por tipo de pagamento.
    """
    try:
        corridas_collection = get_mongo_collection()
        corridas = []
        for corrida in corridas_collection.find({"forma_pagamento": forma_pagamento}):
            corrida['id_corrida'] = str(corrida['_id'])
            corridas.append(CorridaInDB(**corrida))
        return corridas
    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )

@app.get("/", include_in_schema=False)
async def read_index():
    # Constrói o caminho absoluto para o arquivo HTML
    current_dir = pathlib.Path(__file__).parent.parent
    return FileResponse(current_dir / "frontend/index.html")