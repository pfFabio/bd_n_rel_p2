# TransFlow API

API para gerenciamento de corridas de transporte, utilizando arquitetura de microsserviços com FastAPI, RabbitMQ, MongoDB e Redis.

## Funcionalidades

- **Criação de Corridas**: Publica eventos de corrida de forma assíncrona.
- **Consulta de Corridas**: Lista e filtra corridas armazenadas no MongoDB.
- **Consulta de Saldo**: Verifica o saldo de motoristas em tempo real utilizando Redis.
- **Processamento Assíncrono**: Um serviço de consumidor processa as corridas finalizadas para atualizar saldos e persistir dados.
- **Frontend Interativo**: Uma interface simples para interagir com a API.

## Tecnologias Utilizadas

- **Backend**: Python, FastAPI
- **Mensageria**: RabbitMQ
- **Banco de Dados**: MongoDB
- **Cache**: Redis
- **Containerização**: Docker e Docker Compose

## Como Executar (Docker)

Certifique-se de ter o Docker e o Docker Compose instalados em sua máquina.

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/pfFabio/bd_n_rel_p2.git
    cd transflow
    ```

2.  **Inicie os serviços com Docker Compose:**
    Execute o seguinte comando na raiz do projeto:
    ```bash
    docker-compose up --build
    ```
    Este comando irá construir as imagens dos contêineres e iniciar todos os serviços definidos no arquivo `docker-compose.yaml`.

3.  **Acesse a aplicação:**
    - **API (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
    - **Frontend**: [http://localhost:8000/](http://localhost:8000/)
    - **RabbitMQ Management**: [http://localhost:15672/](http://localhost:15672/) (login: guest/guest)

4.  **Para parar a aplicação:**
    Pressione `Ctrl + C` no terminal onde o `docker-compose` está rodando e depois execute:
    ```bash
    docker-compose down
    ```
