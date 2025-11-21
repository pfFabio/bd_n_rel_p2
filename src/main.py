from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
from src.models.corrida_model import Corrida, CorridaInDB
from src.database.mongo_client import MongoClientSingleton, get_mongo_collection
from src.database.redis_client import get_redis_client
import redis
from contextlib import asynccontextmanager
from pymongo.errors import PyMongoError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    MongoClientSingleton().connect()
    # Initialize Redis and set initial balances
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

@app.post("/corridas", response_model=CorridaInDB, status_code=status.HTTP_201_CREATED, tags=["Corridas"])
async def create_corrida(corrida: Corrida):
    """
    Cadastra uma nova corrida no sistema e atualiza o saldo do motorista.
    """
    # 1. Insert into MongoDB
    try:
        corridas_collection = get_mongo_collection()
        corrida_dict = corrida.model_dump()
        result = corridas_collection.insert_one(corrida_dict)
        if not result.inserted_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to insert corrida into database."
            )
        
        inserted_corrida = corridas_collection.find_one({"_id": result.inserted_id})
        if not inserted_corrida:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve inserted corrida."
            )
        
        inserted_corrida['_id'] = str(inserted_corrida['_id'])

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e}"
        )

    # 2. Atomically update driver's balance in Redis
    try:
        redis_client = get_redis_client()
        nome_motorista = corrida.motorista.nome
        valor_corrida = corrida.valor_corrida
        chave_motorista = f"motorista:{nome_motorista}"
        
        # HINCRBYFLOAT is atomic and increments a field within a hash
        redis_client.hincrbyfloat(chave_motorista, "saldo", valor_corrida)

    except redis.exceptions.ConnectionError as e:
        # If Redis fails, we should ideally have a rollback/retry mechanism.
        # For now, we'll raise an error. The corrida was already saved.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Corrida saved to DB, but failed to update driver balance in Redis: {e}"
        )
    except Exception as e:
        # Catch other potential errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while updating balance: {e}"
        )

    return CorridaInDB(**inserted_corrida)


@app.get("/corridas", response_model=List[CorridaInDB], tags=["Corridas"])
async def list_corridas():
    """
    Lista todas as corridas cadastradas no sistema.
    """
    try:
        corridas_collection = get_mongo_collection()
        corridas = []
        for corrida in corridas_collection.find():
            corrida['_id'] = str(corrida['_id'])
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

@app.get("/corridas/{forma_pagamento}", response_model=List[CorridaInDB], tags=["Corridas"])
async def filter_corridas_by_payment(forma_pagamento: str):
    """
    Filtra corridas por tipo de pagamento.
    """
    try:
        corridas_collection = get_mongo_collection()
        corridas = []
        for corrida in corridas_collection.find({"forma_pagamento": forma_pagamento}):
            corrida['_id'] = str(corrida['_id'])
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
    return FileResponse("frontend/index.html")