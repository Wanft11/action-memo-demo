from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    class PublicStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            filename = Path(path).name.lower()
            if filename.endswith((".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3")):
                return Response(status_code=404)
            return await super().get_response(path, scope)

    app.mount("/static", PublicStaticFiles(directory=static_dir), name="static")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Action Memo Demo API is running",
        "demo": "/demo",
        "docs": "/docs",
    }


@app.get("/demo")
def demo() -> FileResponse:
    return FileResponse(static_dir / "index.html")
