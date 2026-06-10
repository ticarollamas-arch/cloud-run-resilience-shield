"""
 _ ___ _                    _   ____             
/ ___| | ___  _   _  __| | |  _ \ _   _ _ __  
| |   | |/ _ \| | | |/ _` | | |_) | | | | '_ \ 
| |___| | (_) | |_| | (_| | |  _ <| |_| | | | |
 \____|_|\___/ \__,_|\__,_| |_| \_\\__,_|_| |_|

Cloud Run Resilience Shield - Otimizador de Workloads contra Indisponibilidades
"""

import logging
import json
import asyncio
from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel, Field

# Configuração de Logging Estruturado
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}'
)
logger = logging.getLogger("resilience_shield")

app = FastAPI(title="Cloud Run Resilience Shield")

# Estado do Circuit Breaker Simples para demonstração
class CircuitBreaker:
    def __init__(self):
        self.is_open = False
        self.failure_count = 0
        self.threshold = 5

breaker = CircuitBreaker()

class PubSubMessage(BaseModel):
    message: dict = Field(..., description="Dados da mensagem do Pub/Sub")
    subscription: str = Field(..., description="Nome da assinatura")

@app.on_event("startup")
async def startup_event():
    logger.info("Serviço inicializado com sucesso. Pronto para receber triggers.")

@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check():
    """Endpoint de Liveness Probe para o Cloud Run"""
    if breaker.is_open:
        return Response(content="{\"status\":\"degraded\"}", media_type="application/json", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "healthy"}

@app.post("/_ah/push", status_code=status.HTTP_200_OK)
async def handle_pubsub_trigger(payload: PubSubMessage):
    """
    Endpoint otimizado para receber triggers do Pub/Sub.
    Garante resiliência contra falhas de processamento.
    """
    if breaker.is_open:
        logger.warning("Circuit Breaker aberto. Rejeitando requisição de forma limpa.")
        return {"status": "ignored", "reason": "circuit_breaker_open"}

    try:
        # Simulação de processamento de negócio
        data = payload.message.get("data")
        if not data:
            # Resiliência Passiva: Payload inválido não deve causar retentativas infinitas
            logger.warning("Payload vazio recebido. Ignorando para evitar loop de retentativas.")
            return {"status": "ignored", "reason": "empty_payload"}
        
        logger.info(f"Processando mensagem com sucesso: {data}")
        breaker.failure_count = 0 # Reset de falhas
        return {"status": "processed"}

    except Exception as e:
        breaker.failure_count += 1
        if breaker.failure_count >= breaker.threshold:
            breaker.is_open = True
            logger.error(f"Circuit Breaker ativado devido a {breaker.failure_count} falhas consecutivas.")
        
        logger.error(f"Erro ao processar trigger: {str(e)}")
        # Retorna 500 para forçar o Pub/Sub a re-enfileirar (com base na política de retry configurada)
        return Response(content=json.dumps({"error": "internal_error"}), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
