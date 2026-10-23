"""Application composition only; add feature endpoints in routes/."""

from receiptflow_common.webapp import create_app

from api_service import admin, dev, usage
from api_service.routes import exports, metadata, receipts, review

app = create_app("receipt-flow api-service")
app.include_router(admin.router)
app.include_router(dev.router)
app.include_router(usage.router)
app.include_router(metadata.router)
app.include_router(receipts.router)
app.include_router(review.router)
app.include_router(exports.router)
