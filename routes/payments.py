import os
import razorpay
import requests

from fastapi import APIRouter, Header, HTTPException

from models import CreateOrderRequest, VerifyPaymentRequest
from utils.auth import get_current_user_id
from utils.seller import get_seller_share
from utils.supabase import SUPABASE_URL, supabase_headers

router = APIRouter()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError("Missing Razorpay environment variables")

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)


@router.post("/api/payments/create-order")
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
        raise HTTPException(
            status_code=400,
            detail="Free notes do not need payment",
        )

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


@router.post("/api/payments/verify")
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
        raise HTTPException(
            status_code=400,
            detail="Invalid payment signature",
        )

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
        raise HTTPException(
            status_code=400,
            detail="You cannot buy your own note",
        )

    existing_purchase = requests.get(
        f"{SUPABASE_URL}/rest/v1/purchases"
        f"?buyer_id=eq.{buyer_id}"
        f"&note_id=eq.{payload.note_id}",
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

    seller_share, seller_level = get_seller_share(
        total_sales,
        is_verified,
    )

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
        raise HTTPException(
            status_code=400,
            detail=purchase_res.text,
        )

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/notes?id=eq.{payload.note_id}",
        headers=headers,
        json={
            "downloads": int(note.get("downloads") or 0) + 1,
        },
        timeout=10,
    )

    new_total_sales = total_sales + 1
    new_wallet_balance = (
        float(seller_profile.get("wallet_balance") or 0)
        + seller_earning
    )

    _, new_seller_level = get_seller_share(
        new_total_sales,
        is_verified,
    )

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