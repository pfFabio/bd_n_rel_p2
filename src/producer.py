import os
from faststream.rabbit import RabbitBroker
from dotenv import load_dotenv

# Carrega as variáveis de ambiente
load_dotenv()

# Configuração do Broker RabbitMQ
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
broker = RabbitBroker(RABBITMQ_URL)