from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .visual_report import build_all_reports


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "work" / "api_uploads"
REPORT_DIR = BASE_DIR / "outputs" / "api_reports"
CACHE_DB = BASE_DIR / "work" / "real_trade_review_cache.sqlite"

app = FastAPI(title="Trade Review Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/reports")
async def create_reports(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xls", ".xlsx", ".csv", ".txt"}:
        raise HTTPException(status_code=400, detail="只支持 xls/xlsx/csv/txt 成交记录文件")

    run_id = uuid4().hex
    run_dir = REPORT_DIR / run_id
    upload_path = UPLOAD_DIR / f"{run_id}{suffix}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(await file.read())

    results = build_all_reports(trades_path=upload_path, output_dir=run_dir, cache_db=CACHE_DB)
    return {
        "run_id": run_id,
        "count": len(results),
        "reports": [
            {
                "title": result.title,
                "rating": result.rating,
                "score": result.score,
                "trade_type": result.trade_type,
                "url": f"/api/reports/{run_id}/{result.output.name}",
            }
            for result in results
        ],
        "index_url": f"/api/reports/{run_id}/index.html",
    }


@app.get("/api/reports/{run_id}/{filename}")
def get_report(run_id: str, filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = REPORT_DIR / run_id / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="报告不存在")
    return FileResponse(path)
