import os
import razorpay
import requests

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client

load_dotenv()

app = FastAPI(title="Notezy API")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError("Missing Razorpay environment variables")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Missing Supabase environment variables")

FRONTEND_URL = os.getenv("FRONTEND_URL")

origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
]

if FRONTEND_URL:
    origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)


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

def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def get_current_user_id(authorization: str):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.replace("Bearer ", "").strip()

    user_res = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )

    if user_res.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = user_res.json()

    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid user")

    return user["id"]


def normalize_storage_path(file_url: str):
    if not file_url:
        return None

    file_path = file_url

    if "/notes/" in file_path:
        file_path = file_path.split("/notes/")[-1]

    if file_path.startswith("notes/"):
        file_path = file_path.replace("notes/", "", 1)

    return file_path


def get_seller_share(total_sales: int, is_verified: bool):
    if is_verified:
        return 0.85, "Notezy Elite"
    if total_sales >= 100:
        return 0.80, "Top Seller"
    if total_sales >= 25:
        return 0.75, "Rising Seller"
    return 0.70, "New Seller"


@app.get("/")
def root():
    return {"message": "Notezy backend is running"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def stats():
    return {
        "notes": 1200,
        "students": 10000,
        "colleges": 50,
    }


@app.post("/api/payments/create-order")
def create_order(payload: CreateOrderRequest):
    headers = supabase_headers()

    note_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/notes?id=eq.{payload.note_id}&select=*",
        headers=headers,
        timeout=10,
    )

    if note_res.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not fetch note")

    notes = note_res.json()

    if not notes:
        raise HTTPException(status_code=404, detail="Note not found")

    note = notes[0]
    amount_paise = int(float(note["price"]) * 100)

    if amount_paise <= 0:
        raise HTTPException(status_code=400, detail="Free notes do not need payment")

    order = razorpay_client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {
                "note_id": payload.note_id,
                "seller_id": note.get("seller_id", ""),
            },
        }
    )

    return {
        "order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "key_id": RAZORPAY_KEY_ID,
        "note": note,
    }


@app.post("/api/payments/verify")
def verify_payment(
    payload: VerifyPaymentRequest,
    authorization: str = Header(None),
):
    buyer_id = get_current_user_id(authorization)

    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    headers = supabase_headers()

    note_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/notes?id=eq.{payload.note_id}&select=*",
        headers=headers,
        timeout=10,
    )

    if note_res.status_code != 200 or not note_res.json():
        raise HTTPException(status_code=404, detail="Note not found")

    note = note_res.json()[0]
    seller_id = note.get("seller_id")
    amount = float(note["price"])

    if seller_id == buyer_id:
        raise HTTPException(status_code=400, detail="You cannot buy your own note")

    existing_purchase = requests.get(
        f"{SUPABASE_URL}/rest/v1/purchases?buyer_id=eq.{buyer_id}&note_id=eq.{payload.note_id}",
        headers=headers,
        timeout=10,
    )

    if existing_purchase.status_code == 200 and existing_purchase.json():
        return {
            "status": "success",
            "message": "Note already unlocked",
            "purchase": existing_purchase.json()[0],
        }

    profile_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{seller_id}&select=*",
        headers=headers,
        timeout=10,
    )

    seller_profile = (
        profile_res.json()[0]
        if profile_res.status_code == 200 and profile_res.json()
        else {}
    )

    total_sales = int(seller_profile.get("total_sales") or 0)
    is_verified = bool(seller_profile.get("is_verified") or False)

    seller_share, seller_level = get_seller_share(total_sales, is_verified)

    seller_earning = round(amount * seller_share, 2)
    platform_fee = round(amount - seller_earning, 2)

    purchase_payload = {
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "note_id": payload.note_id,
        "amount": amount,
        "platform_fee": platform_fee,
        "seller_earning": seller_earning,
        "payment_id": payload.razorpay_payment_id,
    }

    purchase_res = requests.post(
        f"{SUPABASE_URL}/rest/v1/purchases",
        headers=headers,
        json=purchase_payload,
        timeout=10,
    )

    if purchase_res.status_code not in [200, 201]:
        raise HTTPException(status_code=400, detail=purchase_res.text)

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/notes?id=eq.{payload.note_id}",
        headers=headers,
        json={
            "downloads": int(note.get("downloads") or 0) + 1
        },
        timeout=10,
    )

    new_total_sales = total_sales + 1
    new_wallet_balance = (
        float(seller_profile.get("wallet_balance") or 0) + seller_earning
    )

    _, new_seller_level = get_seller_share(new_total_sales, is_verified)

    if seller_id:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{seller_id}",
            headers=headers,
            json={
                "total_sales": new_total_sales,
                "wallet_balance": round(new_wallet_balance, 2),
                "seller_level": new_seller_level,
            },
            timeout=10,
        )

    purchase_data = purchase_res.json()

    return {
        "status": "success",
        "message": "Payment verified and note unlocked",
        "purchase": purchase_data[0] if purchase_data else None,
        "seller_share": seller_share,
        "seller_earning": seller_earning,
        "platform_fee": platform_fee,
        "seller_level": seller_level,
    }


@app.post("/api/download")
def download_note(
    payload: DownloadRequest,
    authorization: str = Header(None),
):
    user_id = get_current_user_id(authorization)
    headers = supabase_headers()

    purchase_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/purchases"
        f"?buyer_id=eq.{user_id}"
        f"&note_id=eq.{payload.note_id}",
        headers=headers,
        timeout=10,
    )

    if purchase_res.status_code != 200 or not purchase_res.json():
        raise HTTPException(
            status_code=403,
            detail="You have not purchased this note."
        )

    note_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/notes"
        f"?id=eq.{payload.note_id}"
        f"&select=file_url",
        headers=headers,
        timeout=10,
    )

    if note_res.status_code != 200 or not note_res.json():
        raise HTTPException(status_code=404, detail="Note not found")

    file_path = normalize_storage_path(note_res.json()[0].get("file_url"))

    if not file_path:
        raise HTTPException(status_code=404, detail="File path not found")

    signed = supabase.storage.from_("notes").create_signed_url(
        file_path,
        300
    )

    return {
        "download_url": signed["signedURL"]
    }

@app.post("/api/wallet/pay")
def wallet_pay(payload: WalletPayRequest, authorization: str = Header(None)):
    buyer_id = get_current_user_id(authorization)
    headers = supabase_headers()

    note_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/notes?id=eq.{payload.note_id}&select=*",
        headers=headers,
        timeout=10,
    )

    if note_res.status_code != 200 or not note_res.json():
        raise HTTPException(status_code=404, detail="Note not found")

    note = note_res.json()[0]
    seller_id = note.get("seller_id")
    price = float(note.get("price") or 0)

    if price <= 0:
        raise HTTPException(status_code=400, detail="This note is free")

    if seller_id == buyer_id:
        raise HTTPException(status_code=400, detail="You cannot buy your own note")

    existing = requests.get(
        f"{SUPABASE_URL}/rest/v1/purchases?buyer_id=eq.{buyer_id}&note_id=eq.{payload.note_id}",
        headers=headers,
        timeout=10,
    )

    if existing.status_code == 200 and existing.json():
        raise HTTPException(status_code=400, detail="Already purchased")

    buyer_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{buyer_id}&select=*",
        headers=headers,
        timeout=10,
    )

    seller_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{seller_id}&select=*",
        headers=headers,
        timeout=10,
    )

    if buyer_res.status_code != 200 or not buyer_res.json():
        raise HTTPException(status_code=404, detail="Buyer profile not found")

    if seller_res.status_code != 200 or not seller_res.json():
        raise HTTPException(status_code=404, detail="Seller profile not found")

    buyer = buyer_res.json()[0]
    seller = seller_res.json()[0]

    buyer_wallet = float(buyer.get("wallet_balance") or 0)

    if buyer_wallet < price:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    total_sales = int(seller.get("total_sales") or 0)
    is_verified = bool(seller.get("is_verified") or False)

    seller_share, _ = get_seller_share(total_sales, is_verified)

    seller_earning = round(price * seller_share, 2)
    platform_fee = round(price - seller_earning, 2)

    purchase_payload = {
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "note_id": payload.note_id,
        "amount": price,
        "platform_fee": platform_fee,
        "seller_earning": seller_earning,
        "payment_id": "WALLET",
    }

    purchase_res = requests.post(
        f"{SUPABASE_URL}/rest/v1/purchases",
        headers=headers,
        json=purchase_payload,
        timeout=10,
    )

    if purchase_res.status_code not in [200, 201]:
        raise HTTPException(status_code=400, detail=purchase_res.text)

    new_buyer_wallet = round(buyer_wallet - price, 2)
    new_seller_wallet = round(float(seller.get("wallet_balance") or 0) + seller_earning, 2)
    new_total_sales = total_sales + 1
    _, new_seller_level = get_seller_share(new_total_sales, is_verified)

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{buyer_id}",
        headers=headers,
        json={"wallet_balance": new_buyer_wallet},
        timeout=10,
    )

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{seller_id}",
        headers=headers,
        json={
            "wallet_balance": new_seller_wallet,
            "total_sales": new_total_sales,
            "seller_level": new_seller_level,
        },
        timeout=10,
    )

    requests.post(
        f"{SUPABASE_URL}/rest/v1/wallet_transactions",
        headers=headers,
        json={
            "user_id": buyer_id,
            "type": "debit",
            "amount": price,
            "description": f"Purchased {note.get('title')}",
            "reference_id": payload.note_id,
        },
        timeout=10,
    )

    requests.post(
        f"{SUPABASE_URL}/rest/v1/wallet_transactions",
        headers=headers,
        json={
            "user_id": seller_id,
            "type": "credit",
            "amount": seller_earning,
            "description": f"Sold {note.get('title')}",
            "reference_id": payload.note_id,
        },
        timeout=10,
    )

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/notes?id=eq.{payload.note_id}",
        headers=headers,
        json={"downloads": int(note.get("downloads") or 0) + 1},
        timeout=10,
    )

    return {
        "status": "success",
        "message": "Purchased using wallet",
        "wallet_balance": new_buyer_wallet,
        "seller_earning": seller_earning,
        "platform_fee": platform_fee,
    }