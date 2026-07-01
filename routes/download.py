import requests
from fastapi import APIRouter, Header, HTTPException

from models import DownloadRequest
from utils.auth import get_current_user_id
from utils.storage import normalize_storage_path
from utils.supabase import SUPABASE_URL, supabase_headers, supabase

router = APIRouter()


@router.post("/api/download")
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
            detail="You have not purchased this note.",
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
        300,
    )

    return {
        "download_url": signed["signedURL"],
    }