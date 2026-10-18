"""
FastAPI router for extraction endpoints.

Mount this router in main.py with:
    from backend.extraction.router import router as extraction_router
    app.include_router(extraction_router, prefix="/extraction", tags=["extraction"])
"""

from fastapi import APIRouter

from backend.app.schemas import ClassifyMerchantRequest, ClassifyMerchantResult
from backend.extraction.merchants import classify_merchant

router = APIRouter()


@router.post("/classify-merchant", response_model=ClassifyMerchantResult)
async def classify_merchant_endpoint(
    request: ClassifyMerchantRequest,
) -> ClassifyMerchantResult:
    """
    Classify an unknown merchant by domain.
    
    Uses a cascade of methods:
    1. Exact domain match against seed merchants
    2. Fuzzy name matching (if page_title provided)
    3. Embedding similarity search
    4. Fallback to inferred category
    
    Returns merchant details with confidence score.
    """
    return classify_merchant(
        name=request.page_title,
        domain=request.domain,
    )
