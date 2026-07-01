import requests
from fastapi import HTTPException

from utils.supabase import SUPABASE_URL, supabase_headers


def get_profile(user_id: str):
    headers = supabase_headers()

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*",
        headers=headers,
        timeout=10,
    )

    if res.status_code != 200 or not res.json():
        raise HTTPException(status_code=404, detail="Profile not found")

    return res.json()[0]


def update_wallet(user_id: str, wallet_balance: float):
    headers = supabase_headers()

    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
        headers=headers,
        json={
            "wallet_balance": round(wallet_balance, 2),
        },
        timeout=10,
    )

    if res.status_code not in [200, 204]:
        raise HTTPException(status_code=400, detail=res.text)


def add_wallet_transaction(
    user_id: str,
    tx_type: str,
    amount: float,
    description: str,
    reference_id=None,
):
    headers = supabase_headers()

    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/wallet_transactions",
        headers=headers,
        json={
            "user_id": user_id,
            "type": tx_type,
            "amount": round(amount, 2),
            "description": description,
            "reference_id": reference_id,
        },
        timeout=10,
    )

    if res.status_code not in [200, 201]:
        raise HTTPException(status_code=400, detail=res.text)