import os
from faststream import FastStream, Logger
from src.producer import broker  # Importa o broker compartilhado
from src.models.corrida_model import Corrida
from src.database.redis_client import get_redis_client
from src.database.mongo_client import MongoClientSingleton, get_mongo_collection
from pymongo.errors import PyMongoError
import redis
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env (se existir) e do sistema
load_dotenv()

# Configuração da Aplicação FastStream com o broker compartilhado
app = FastStream(broker)

@app.on_startup
async def startup():
    """Conecta aos bancos de dados na inicialização do consumer."""
    MongoClientSingleton().connect()

@app.on_shutdown
async def shutdown():
    """Fecha a conexão com o MongoDB ao encerrar o consumer."""
    MongoClientSingleton().close()

@broker.subscriber("corridas_queue")
async def on_corrida_finalizada(msg: dict, logger: Logger):
    """
    Consome o evento 'corrida_finalizada', salva no MongoDB e atualiza o saldo no Redis.
    """
    logger.info(f"Recebida nova corrida para processar: {msg.get('id_corrida')}")

    corrida_obj = Corrida(**msg)

    # 1. Salvar a corrida no MongoDB
    try:
        corridas_collection = get_mongo_collection()
        # MongoDB will automatically generate an _id for the document
        result = corridas_collection.insert_one(msg)
        if not result.inserted_id:
            logger.error("Falha ao inserir corrida no MongoDB.")
            # Aqui você poderia reenfileirar a mensagem ou movê-la para uma dead-letter queue
            return
        logger.info(f"Corrida {msg.get('id_corrida')} salva no MongoDB com sucesso.")
    except PyMongoError as e:
        logger.error(f"Erro de banco de dados ao salvar corrida: {e}")
        return

    # 2. Atualizar o saldo do motorista no Redis
    try:
        redis_client = get_redis_client()
        nome_motorista = corrida_obj.motorista.nome
        valor_corrida = corrida_obj.valor_corrida
        chave_motorista = f"motorista:{nome_motorista}"
        
        redis_client.hincrbyfloat(chave_motorista, "saldo", valor_corrida)
        logger.info(f"Saldo do motorista {nome_motorista} atualizado.")
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Erro de conexão com Redis ao atualizar saldo: {e}")
        # Idealmente, teríamos uma lógica de compensação aqui, como remover a corrida do MongoDB.
    except Exception as e:
        logger.error(f"Erro inesperado ao atualizar saldo: {e}")
