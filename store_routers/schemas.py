from pydantic import BaseModel
from typing import List, Optional


class CartItem(BaseModel):
    stock_key: str
    price: float = 0
    currency: str
    quantity: int
    player_id: Optional[str] = ''
    player_name: Optional[str] = ''
    scheduled_time: Optional[str] = ''


class CheckoutRequest(BaseModel):
    cart: List[CartItem]
    transaction_id: Optional[str] = ''


class StoreCheckoutError(Exception):
    def __init__(self, message: str, status_code: int = 400, *, force_logout: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.force_logout = force_logout

