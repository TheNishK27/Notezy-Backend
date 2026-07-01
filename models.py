from pydantic import BaseModel


class CreateOrderRequest(BaseModel):
    note_id: str


class VerifyPaymentRequest(BaseModel):
    note_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class DownloadRequest(BaseModel):
    note_id: str


class WalletPayRequest(BaseModel):
    note_id: str