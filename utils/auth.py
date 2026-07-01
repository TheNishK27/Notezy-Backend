import requests
from fastapi import HTTPException

from utils.supabase import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY


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