import json
from src.database.redis_client import get_redis_client

def consume_corridas():
    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()
    pubsub.subscribe('corridas')
    
    print("Consumidor de corridas iniciado. Aguardando mensagens...")
    
    try:
        for message in pubsub.listen():
            if message['type'] == 'message':
                corrida_data = json.loads(message['data'])
                print("Nova corrida recebida:", corrida_data)
    except KeyboardInterrupt:
        print("Consumidor de corridas encerrado.")
    finally:
        pubsub.close()

if __name__ == "__main__":
    consume_corridas()
