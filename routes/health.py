from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return {"message": "Notezy backend is running"}


@router.get("/api/health")
def health():
    return {"status": "ok"}