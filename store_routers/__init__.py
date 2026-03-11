from fastapi import APIRouter

from .storefront import router as storefront_router
from .admin_staff import router as admin_staff_router
from .admin_catalog import router as admin_catalog_router
from .admin_orders import router as admin_orders_router
from .chat import router as chat_router
from .admin_wallet import router as admin_wallet_router

router = APIRouter()
router.include_router(storefront_router)
router.include_router(admin_staff_router)
router.include_router(admin_catalog_router)
router.include_router(admin_orders_router)
router.include_router(chat_router)
router.include_router(admin_wallet_router)

__all__ = ["router"]
