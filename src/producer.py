import json
from src.database.redis_client import get_redis_client
from src.models.corrida_model import Corrida

def publish_corrida(corrida: Corrida):
    redis_client = get_redis_client()
    channel = 'corridas'
    message = json.dumps(corrida.dict())
    redis_client.publish(channel, message)