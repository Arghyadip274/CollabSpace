from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge

router = APIRouter(tags=["Metrics"])

# Define Prometheus metrics
WS_CONNECTIONS = Gauge(
    "active_ws_connections", 
    "Number of active WebSocket connections"
)

MESSAGES_PUBLISHED = Counter(
    "messages_published_total", 
    "Total number of messages published via WebSockets"
)

ACTIVE_ROOMS = Gauge(
    "active_document_rooms", 
    "Number of active rooms being managed by this backend node"
)

@router.get("/metrics")
def get_metrics():
    """
    Exposes metrics in Prometheus format.
    """
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
