from fastapi import APIRouter

router = APIRouter()


@router.get("/api/stats")
def stats():
    return {
        "notes": 1200,
        "students": 10000,
        "colleges": 50,
    }