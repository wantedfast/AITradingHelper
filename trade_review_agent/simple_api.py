from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import threading
import traceback
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from .alerts import AlertPlan, evaluate_plans, event_dedupe_key, load_plans, save_plans
from .ai_trade_parser import OpenAITradeParsingError
from .config import load_env
from .ocr_trades import trade_file_to_trade_csv
from .visual_report import build_all_reports
from .workbench_agents import normalize_research_model_tier
from .voice_settings import VoiceSettings, load_voice_settings, normalize_voice_settings, save_voice_settings, voice_settings_payload
from .watch_agent import build_watch_plan, narrate_alert_event, preview_voice_line
from .watch_form_ocr import extract_watch_form_from_image


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "work" / "api_uploads"
REPORT_DIR = BASE_DIR / "outputs" / "api_reports"
CACHE_DB = BASE_DIR / "work" / "real_trade_review_cache.sqlite"
ALERT_PLANS = BASE_DIR / "work" / "alert_plans.json"
VOICE_SETTINGS_PATH = BASE_DIR / "work" / "watch_voice_settings.json"
WATCH_AUDIO_DIR = BASE_DIR / "work" / "tts"
WATCH_SEEN_EVENTS = BASE_DIR / "work" / "watch_seen_events.json"
API_ERROR_LOG = BASE_DIR / "work" / "api_errors.log"
CN_TZ = ZoneInfo("Asia/Shanghai")
ALLOWED_SUFFIXES = {".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
MAX_SEEN_EVENTS = 2048
REPORT_MANIFEST_NAME = "report_manifest.json"
REPORT_STATUS_NAME = "report_status.json"
RESEARCH_PRESENTER_NAME = "research_presenter_data.json"
RESEARCH_WORKBENCH_NAME = "research_workbench_data.json"


class SingleInstanceThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class TradeReviewHandler(BaseHTTPRequestHandler):
    server_version = "TradeReviewAgent/0.2"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        self._begin_request()
        path = self._request_path()
        try:
            if path == "/api/health":
                self._json({"status": "ok"})
                return
            if path.startswith("/api/reports/"):
                self._serve_report(path)
                return
            if path == "/api/watch/plans":
                self._json({"plans": [_plan_payload(plan) for plan in load_plans(ALERT_PLANS)]})
                return
            if path == "/api/watch/voice-settings":
                settings = load_voice_settings(VOICE_SETTINGS_PATH)
                self._json(voice_settings_payload(settings))
                return
            if path.startswith("/api/watch/audio/"):
                self._serve_watch_audio(path)
                return
            self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._send_error(exc)

    def do_POST(self) -> None:
        self._begin_request()
        path = self._request_path()
        try:
            if path == "/api/reports":
                self._create_reports()
                return
            if path == "/api/watch/plans":
                self._create_watch_plan()
                return
            if path == "/api/watch/plans/clear":
                self._clear_watch_plans()
                return
            if path == "/api/watch/poll":
                self._poll_watch_plans()
                return
            if path == "/api/watch/ocr":
                self._extract_watch_form_ocr()
                return
            if path == "/api/watch/voice-settings":
                self._save_watch_voice_settings()
                return
            if path == "/api/watch/voice-preview":
                self._preview_watch_voice()
                return
            self._json({"error": "not found"}, status=404)
        except ValueError as exc:
            self._send_error(exc, status=400)
        except Exception as exc:
            self._send_error(exc)

    def _create_reports(self) -> None:
        self._create_reports_resilient()

    def _create_reports_resilient(self) -> None:
        run_id = ""
        run_dir: Path | None = None
        try:
            self._set_stage("parse_multipart")
            content_type = self.headers.get("content-type", "")
            if "multipart/form-data" not in content_type:
                self._json({"error": "expected multipart/form-data"}, status=400)
                return

            filename, data, fields = self._read_multipart_form(content_type)
            if not filename or data is None:
                self._json({"error": "missing file"}, status=400)
                return
            research_model_tier = normalize_research_model_tier(fields.get("research_model_tier") or fields.get("better_report"))

            filename = Path(filename or "upload.csv").name
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                self._json({"error": "仅支持 xls/xlsx/csv/txt 成交记录文件或 png/jpg/jpeg/webp 成交截图"}, status=400)
                return

            self._set_stage("create_run")
            run_id = uuid4().hex
            run_dir = REPORT_DIR / run_id
            self._set_stage("write_upload", run_id=run_id)
            upload_path = UPLOAD_DIR / f"{run_id}{suffix}"
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            upload_path.write_bytes(data)

            self._set_stage("queued", run_id=run_id)
            _write_report_status(run_id, run_dir, status="queued", stage="queued", request_id=self._request_id)
            _start_report_generation_task(
                run_id=run_id,
                run_dir=run_dir,
                upload_path=upload_path,
                research_model_tier=research_model_tier,
                request_id=self._request_id,
            )
            self._json(_report_status_payload(run_id, status="queued", stage="queued"), status=202)
        except Exception as exc:
            recovered = _recover_report_manifest(run_id, run_dir) if run_id and run_dir else None
            if recovered:
                _write_api_error(
                    request_id=self._request_id,
                    method=self.command,
                    path=self._request_path(),
                    run_id=run_id,
                    stage=self._stage,
                    exc=exc,
                    recovered=True,
                )
                recovered["warning"] = "report generation recovered from completed artifacts"
                recovered["error"] = "Recovered after report generation error"
                recovered["detail"] = str(exc)
                recovered["request_id"] = self._request_id
                recovered["stage"] = self._stage
                recovered["run_id"] = run_id
                self._json(recovered)
                return
            raise

    def _create_watch_plan(self) -> None:
        payload = self._read_json_body()
        stock_name = str(payload.get("stock_name") or "").strip()
        buy_date = str(payload.get("buy_date") or "").strip()
        position = str(payload.get("position") or "").strip()
        buy_price = _optional_float(payload.get("buy_price"))
        if not stock_name:
            raise ValueError("请填写股票名称")
        if not buy_date:
            raise ValueError("请填写买入时间")
        if not position:
            raise ValueError("请填写仓位")
        if buy_price is None:
            raise ValueError("请填写买入价")

        plan = build_watch_plan(
            stock_name=stock_name,
            buy_date=buy_date,
            position=position,
            buy_price=buy_price,
            cache_db=CACHE_DB,
        )
        plans = [item for item in load_plans(ALERT_PLANS) if item.plan_id != plan.plan_id]
        plans.insert(0, plan)
        save_plans(ALERT_PLANS, plans)
        self._json({"plan": _plan_payload(plan), "plans": [_plan_payload(item) for item in plans]})

    def _clear_watch_plans(self) -> None:
        save_plans(ALERT_PLANS, [])
        _save_seen_event_map(WATCH_SEEN_EVENTS, {})
        self._json({"plans": []})

    def _poll_watch_plans(self) -> None:
        _ = self._read_json_body()
        plans = load_plans(ALERT_PLANS)
        quotes, candidate_events, errors = evaluate_plans(plans)
        seen_map = _load_seen_event_map(WATCH_SEEN_EVENTS)
        voice_settings = load_voice_settings(VOICE_SETTINGS_PATH)
        fresh_events: list[dict] = []
        plans_changed = False

        for event in candidate_events:
            key = event_dedupe_key(event)
            if key in seen_map:
                continue

            payload = _event_payload(event, voice_settings, errors)
            fresh_events.append(payload)
            seen_map[key] = payload["occurred_at"]

            response_id = payload.get("agent_response_id", "")
            if response_id and event.plan.agent_response_id != response_id:
                event.plan.agent_response_id = response_id
                plans_changed = True

        if plans_changed:
            save_plans(ALERT_PLANS, plans)
        _save_seen_event_map(WATCH_SEEN_EVENTS, seen_map)

        self._json(
            {
                "plans": [_plan_payload(plan) for plan in plans],
                "quotes": [asdict(quote) for quote in quotes],
                "events": fresh_events,
                "errors": errors,
            }
        )

    def _extract_watch_form_ocr(self) -> None:
        content_type = self.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            self._json({"error": "expected multipart/form-data"}, status=400)
            return

        filename, data = self._read_multipart_file(content_type)
        if not filename or data is None:
            self._json({"error": "missing file"}, status=400)
            return

        filename = Path(filename or "watch-ocr.jpg").name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            self._json({"error": "OCR 仅支持 png/jpg/jpeg/webp 图片"}, status=400)
            return

        run_id = uuid4().hex
        upload_path = UPLOAD_DIR / f"watch_ocr_{run_id}{suffix}"
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(data)

        fields = extract_watch_form_from_image(upload_path)
        self._json({"fields": fields})

    def _save_watch_voice_settings(self) -> None:
        payload = self._read_json_body()
        settings = normalize_voice_settings(payload)
        saved = save_voice_settings(VOICE_SETTINGS_PATH, settings)
        self._json(voice_settings_payload(saved))

    def _preview_watch_voice(self) -> None:
        payload = self._read_json_body()
        settings = normalize_voice_settings(payload)
        preview = preview_voice_line(settings.preview_text, WATCH_AUDIO_DIR, settings)
        result = {
            "voice_line": str(preview.get("voice_line") or settings.preview_text),
            "provider": str(preview.get("provider") or settings.provider),
            "voice": str(
                preview.get("voice")
                or (settings.openai_voice if settings.provider == "openai" else settings.edge_voice)
            ),
        }
        audio_url = _audio_url(preview.get("audio_path"))
        if audio_url:
            result["audio_url"] = audio_url
        self._json(result)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("content-length", "0") or 0)
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw.strip():
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _read_multipart_file(self, content_type: str) -> tuple[str, bytes | None]:
        filename, data, _ = self._read_multipart_form(content_type)
        return filename, data

    def _read_multipart_form(self, content_type: str) -> tuple[str, bytes | None, dict[str, str]]:
        match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
        if not match:
            return "", None, {}
        boundary = match.group("boundary").strip().strip('"').encode("utf-8")
        content_length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(content_length)
        marker = b"--" + boundary
        filename = ""
        file_content: bytes | None = None
        fields: dict[str, str] = {}
        for raw_part in body.split(marker):
            if b"\r\n\r\n" not in raw_part:
                continue
            header_bytes, content = raw_part.split(b"\r\n\r\n", 1)
            header_text = header_bytes.decode("utf-8", errors="ignore")
            content = content.rstrip(b"\r\n")
            name_match = re.search(r'name="(?P<name>[^"]*)"', header_text)
            field_name = name_match.group("name") if name_match else ""
            if field_name == "file" and b"filename=" in header_bytes:
                filename_match = re.search(r'filename="(?P<filename>[^"]*)"', header_text)
                filename = filename_match.group("filename") if filename_match else "upload.csv"
                file_content = content
            elif field_name:
                fields[field_name] = content.decode("utf-8", errors="ignore").strip()
        return filename, file_content, fields

    def _serve_report(self, path: str) -> None:
        parts = path.split("/")
        if len(parts) != 5:
            self._json({"error": "not found"}, status=404)
            return
        run_id = parts[3]
        filename = Path(unquote(parts[4])).name
        run_dir = REPORT_DIR / run_id
        if filename == "status":
            self._serve_report_status(run_id, run_dir)
            return
        report_path = _resolve_report_file(run_id, run_dir, filename)
        if not report_path.exists() or not report_path.is_file():
            self._json({"error": "report not found"}, status=404)
            return
        self._serve_file(report_path)

    def _serve_report_status(self, run_id: str, run_dir: Path) -> None:
        recovered = _recover_report_manifest(run_id, run_dir)
        if recovered:
            recovered["status"] = "done"
            recovered["stage"] = "done"
            recovered["status_url"] = f"/api/reports/{run_id}/status"
            self._json(recovered)
            return
        status_path = run_dir / REPORT_STATUS_NAME
        if not status_path.exists():
            self._json(_report_status_payload(run_id, status="queued", stage="queued"))
            return
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._json(_api_error_payload(exc, request_id=getattr(self, "_request_id", ""), run_id=run_id, stage="read_status"), status=500)
            return
        self._json(payload)

    def _serve_watch_audio(self, path: str) -> None:
        parts = path.split("/")
        if len(parts) != 5:
            self._json({"error": "not found"}, status=404)
            return
        filename = Path(unquote(parts[4])).name
        audio_path = WATCH_AUDIO_DIR / filename
        if not audio_path.exists() or not audio_path.is_file():
            self._json({"error": "audio not found"}, status=404)
            return
        self._serve_file(audio_path)

    def _serve_file(self, file_path: Path) -> None:
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _request_path(self) -> str:
        return urlparse(self.path).path

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _begin_request(self) -> None:
        self._request_id = uuid4().hex
        self._run_id = ""
        self._stage = "route"

    def _set_stage(self, stage: str, *, run_id: str | None = None) -> None:
        self._stage = stage
        if run_id is not None:
            self._run_id = run_id

    def _send_error(self, exc: Exception, status: int = 500) -> None:
        request_id = getattr(self, "_request_id", uuid4().hex)
        run_id = getattr(self, "_run_id", "")
        stage = getattr(self, "_stage", "unknown")
        response_status = _api_error_status(exc, status)
        _write_api_error(
            request_id=request_id,
            method=self.command,
            path=self._request_path(),
            run_id=run_id,
            stage=stage,
            exc=exc,
            recovered=False,
        )
        self._json(
            _api_error_payload(exc, request_id=request_id, run_id=run_id, stage=stage),
            status=response_status,
        )


def _plan_payload(plan: AlertPlan) -> dict:
    return asdict(plan)


def _start_report_generation_task(
    *,
    run_id: str,
    run_dir: Path,
    upload_path: Path,
    research_model_tier: str,
    request_id: str,
) -> None:
    thread = threading.Thread(
        target=_run_report_generation_task,
        kwargs={
            "run_id": run_id,
            "run_dir": run_dir,
            "upload_path": upload_path,
            "research_model_tier": research_model_tier,
            "request_id": request_id,
        },
        daemon=True,
        name=f"report-{run_id[:8]}",
    )
    thread.start()


def _run_report_generation_task(
    *,
    run_id: str,
    run_dir: Path,
    upload_path: Path,
    research_model_tier: str,
    request_id: str,
) -> None:
    stage = "queued"
    try:
        stage = "ocr_trade_file"
        _write_report_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        trades_path = run_dir / "ai_trades.csv"
        trade_file_to_trade_csv(upload_path, trades_path)

        stage = "build_reports"
        _write_report_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        results = build_all_reports(
            trades_path=trades_path,
            output_dir=run_dir,
            cache_db=CACHE_DB,
            research_model_tier=research_model_tier,
        )

        stage = "write_aliases"
        _write_report_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        _ensure_report_aliases(run_dir)

        stage = "write_manifest"
        _write_report_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        manifest = _report_manifest(run_id, results)
        (run_dir / REPORT_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        done = dict(manifest)
        done["status"] = "done"
        done["stage"] = "done"
        done["status_url"] = f"/api/reports/{run_id}/status"
        _write_report_status_payload(run_dir, done)
    except Exception as exc:
        recovered = _recover_report_manifest(run_id, run_dir)
        if recovered:
            recovered["status"] = "done"
            recovered["stage"] = "done"
            recovered["status_url"] = f"/api/reports/{run_id}/status"
            recovered["warning"] = "report generation recovered from completed artifacts"
            _write_report_status_payload(run_dir, recovered)
            return
        payload = _report_status_payload(run_id, status="error", stage=stage, request_id=request_id)
        payload.update(_api_error_payload(exc, request_id=request_id, run_id=run_id, stage=stage))
        payload["status"] = "error"
        _write_report_status_payload(run_dir, payload)
        _write_api_error(
            request_id=request_id,
            method="BACKGROUND",
            path=f"/api/reports/{run_id}",
            run_id=run_id,
            stage=stage,
            exc=exc,
            recovered=False,
        )


def _report_status_payload(run_id: str, *, status: str, stage: str, request_id: str = "") -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "status_url": f"/api/reports/{run_id}/status",
        "manifest_url": f"/api/reports/{run_id}/{REPORT_MANIFEST_NAME}",
        "research_workbench_url": f"/api/reports/{run_id}/{RESEARCH_WORKBENCH_NAME}",
        "research_presenter_url": f"/api/reports/{run_id}/{RESEARCH_PRESENTER_NAME}",
        "request_id": request_id,
    }


def _write_report_status(run_id: str, run_dir: Path, *, status: str, stage: str, request_id: str = "") -> None:
    _write_report_status_payload(run_dir, _report_status_payload(run_id, status=status, stage=stage, request_id=request_id))


def _write_report_status_payload(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / REPORT_STATUS_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _recover_report_manifest(run_id: str, run_dir: Path | None) -> dict | None:
    if not run_id or run_dir is None or not run_dir.exists():
        return None
    _ensure_report_aliases(run_dir)
    manifest_path = run_dir / REPORT_MANIFEST_NAME
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = _manifest_from_run_dir(run_id, run_dir)
    else:
        manifest = _manifest_from_run_dir(run_id, run_dir)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not isinstance(manifest, dict) or not manifest.get("reports"):
        return None
    return manifest


def _api_error_payload(exc: Exception, *, request_id: str, run_id: str = "", stage: str = "") -> dict:
    if isinstance(exc, OpenAITradeParsingError):
        payload = {
            "error": exc.user_message,
            "detail": _openai_error_detail(exc),
            "code": exc.code,
            "retryable": exc.retryable,
            "request_id": request_id,
            "run_id": run_id,
            "stage": stage,
        }
        if exc.retry_after is not None:
            payload["retry_after"] = exc.retry_after
        return payload
    return {
        "error": "Internal Server Error",
        "detail": str(exc),
        "request_id": request_id,
        "run_id": run_id,
        "stage": stage,
    }


def _api_error_status(exc: Exception, fallback: int = 500) -> int:
    if isinstance(exc, OpenAITradeParsingError):
        if exc.status_code == 429:
            return 429
        if exc.status_code in {400, 401, 403, 404}:
            return 502
        if exc.status_code and 500 <= exc.status_code <= 599:
            return 503
        return 503 if exc.retryable else 502
    return fallback


def _openai_error_detail(exc: OpenAITradeParsingError) -> str:
    if exc.status_code == 429:
        return "OpenAI 请求过于频繁，已重试后仍被限流"
    if exc.status_code in {500, 502, 503, 504}:
        return f"OpenAI 服务临时异常（HTTP {exc.status_code}），已重试后仍失败"
    if exc.status_code:
        return f"OpenAI 解析请求失败（HTTP {exc.status_code}）"
    return "OpenAI 解析请求失败"


def _write_api_error(
    *,
    request_id: str,
    method: str,
    path: str,
    run_id: str,
    stage: str,
    exc: Exception,
    recovered: bool,
) -> None:
    try:
        API_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "time": datetime.now(CN_TZ).isoformat(),
            "method": method,
            "path": path,
            "request_id": request_id,
            "run_id": run_id,
            "stage": stage,
            "recovered": recovered,
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
        }
        with API_ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        print(f"[warn] failed to write API error log for {request_id}", flush=True)


def _resolve_report_file(run_id: str, run_dir: Path, filename: str) -> Path:
    report_path = run_dir / filename
    if report_path.exists() and report_path.is_file():
        return report_path
    if not run_dir.exists() or not run_dir.is_dir():
        return report_path

    if filename == RESEARCH_PRESENTER_NAME:
        _copy_first_artifact_if_missing(run_dir, RESEARCH_PRESENTER_NAME, "*.presenter.json")
        return _first_report_artifact(run_dir, "*.presenter.json") or report_path
    if filename == RESEARCH_WORKBENCH_NAME:
        _copy_first_artifact_if_missing(run_dir, RESEARCH_WORKBENCH_NAME, "*.workbench.json")
        return _first_report_artifact(run_dir, "*.workbench.json") or report_path
    if filename == REPORT_MANIFEST_NAME:
        _ensure_report_aliases(run_dir)
        manifest_path = run_dir / REPORT_MANIFEST_NAME
        manifest = _manifest_from_run_dir(run_id, run_dir)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path
    return report_path


def _ensure_report_aliases(run_dir: Path) -> None:
    _copy_first_artifact_if_missing(run_dir, RESEARCH_PRESENTER_NAME, "*.presenter.json")
    _copy_first_artifact_if_missing(run_dir, RESEARCH_WORKBENCH_NAME, "*.workbench.json")


def _copy_first_artifact_if_missing(run_dir: Path, alias_name: str, pattern: str) -> None:
    alias_path = run_dir / alias_name
    if alias_path.exists():
        return
    source = _first_report_artifact(run_dir, pattern)
    if source:
        alias_path.write_bytes(source.read_bytes())


def _first_report_artifact(run_dir: Path, pattern: str) -> Path | None:
    matches = sorted(path for path in run_dir.glob(pattern) if path.is_file())
    return matches[0] if matches else None


def _manifest_from_run_dir(run_id: str, run_dir: Path) -> dict:
    reports = []
    html_files = sorted(path for path in run_dir.glob("*.html") if path.is_file() and path.name != "index.html")
    for html_path in html_files:
        workbench_path = html_path.with_suffix(".workbench.json")
        presenter_path = html_path.with_suffix(".presenter.json")
        metadata = _report_metadata_from_workbench(workbench_path)
        html_url = f"/api/reports/{run_id}/{html_path.name}"
        workbench_url = f"/api/reports/{run_id}/{workbench_path.name}"
        presenter_url = f"/api/reports/{run_id}/{presenter_path.name}"
        reports.append(
            {
                "title": _report_title_from_artifacts(presenter_path, workbench_path, html_path.stem),
                "rating": "",
                "score": 0,
                "trade_type": "",
                "requested_research_model_tier": metadata["requested_tier"],
                "research_model_tier": metadata["tier"],
                "actual_research_model_tier": metadata["tier"],
                "wang_model": metadata["wang_model"],
                "public_equity_model": metadata["public_equity_model"],
                "url": html_url,
                "html_url": html_url,
                "workbench_url": workbench_url,
                "presenter_url": presenter_url,
            }
        )
    return _manifest_payload(run_id, reports)


def _report_metadata_from_workbench(path: Path) -> dict[str, str]:
    fallback = {"requested_tier": "standard", "tier": "standard", "wang_model": "gpt-4.1", "public_equity_model": "gpt-4.1"}
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    research_model = data.get("research_model") if isinstance(data, dict) else {}
    if not isinstance(research_model, dict):
        return fallback
    requested_research_model = data.get("requested_research_model") if isinstance(data, dict) else {}
    requested_tier = normalize_research_model_tier(requested_research_model.get("tier")) if isinstance(requested_research_model, dict) else fallback["requested_tier"]
    tier = normalize_research_model_tier(research_model.get("tier"))
    default_model = "gpt-5.5" if tier == "better" else "gpt-4.1"
    model = str(research_model.get("model") or default_model)
    return {
        "requested_tier": requested_tier,
        "tier": tier,
        "wang_model": str(research_model.get("wang_model") or model),
        "public_equity_model": str(research_model.get("public_equity_model") or model),
    }


def _report_title_from_stem(stem: str) -> str:
    parts = stem.split("_")
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return stem


def _report_title_from_artifacts(presenter_path: Path, workbench_path: Path, stem: str) -> str:
    for path in (presenter_path, workbench_path):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        company = data.get("company") if isinstance(data, dict) else {}
        if not isinstance(company, dict):
            continue
        name = str(company.get("name") or "").strip()
        code = str(company.get("code") or "").strip()
        if name and code:
            return f"{name} {code}"
        if name:
            return name
    return _report_title_from_stem(stem)


def _report_manifest(run_id: str, results: list) -> dict:
    reports = []
    for result in results:
        html_url = f"/api/reports/{run_id}/{result.output.name}"
        workbench_url = f"/api/reports/{run_id}/{result.output.with_suffix('.workbench.json').name}"
        presenter_url = f"/api/reports/{run_id}/{result.output.with_suffix('.presenter.json').name}"
        reports.append(
            {
                "title": result.title,
                "rating": result.rating,
                "score": result.score,
                "trade_type": result.trade_type,
                "requested_research_model_tier": getattr(result, "requested_research_model_tier", getattr(result, "research_model_tier", "standard")),
                "research_model_tier": getattr(result, "research_model_tier", "standard"),
                "actual_research_model_tier": getattr(result, "research_model_tier", "standard"),
                "wang_model": getattr(result, "wang_model", "gpt-4.1"),
                "public_equity_model": getattr(result, "public_equity_model", "gpt-4.1"),
                "url": html_url,
                "html_url": html_url,
                "workbench_url": workbench_url,
                "presenter_url": presenter_url,
            }
        )
    return _manifest_payload(run_id, reports)


def _manifest_payload(run_id: str, reports: list[dict]) -> dict:
    first = reports[0] if reports else {}
    manifest_url = f"/api/reports/{run_id}/{REPORT_MANIFEST_NAME}"
    return {
        "run_id": run_id,
        "count": len(reports),
        "reports": reports,
        "index_url": f"/api/reports/{run_id}/index.html",
        "manifest_url": manifest_url,
        "presenter_manifest_url": manifest_url,
        "html_url": first.get("html_url", ""),
        "presenter_url": first.get("presenter_url", ""),
        "workbench_url": first.get("workbench_url", ""),
        "requested_research_model_tier": first.get("requested_research_model_tier", first.get("research_model_tier", "standard")),
        "research_model_tier": first.get("research_model_tier", "standard"),
        "actual_research_model_tier": first.get("actual_research_model_tier", first.get("research_model_tier", "standard")),
        "wang_model": first.get("wang_model", "gpt-4.1"),
        "public_equity_model": first.get("public_equity_model", "gpt-4.1"),
        "research_workbench_url": f"/api/reports/{run_id}/{RESEARCH_WORKBENCH_NAME}",
        "research_presenter_url": f"/api/reports/{run_id}/{RESEARCH_PRESENTER_NAME}",
    }


def _event_payload(event, settings: VoiceSettings, errors: list[str]) -> dict:
    occurred_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    voice_name = settings.openai_voice if settings.provider == "openai" else settings.edge_voice
    message = event.message
    voice_line = event.plan.voice_line or event.message
    audio_url = ""
    response_id = ""
    try:
        narration = narrate_alert_event(event, WATCH_AUDIO_DIR, settings)
        message = str(narration.get("message") or message)
        voice_line = str(narration.get("voice_line") or voice_line)
        audio_url = _audio_url(narration.get("audio_path"))
        response_id = str(narration.get("agent_response_id") or "")
    except Exception as exc:
        errors.append(f"{event.plan.code}: 提醒语音生成失败 - {exc}")

    payload = {
        "key": event_dedupe_key(event),
        "plan_id": event.plan.plan_id,
        "code": event.plan.code,
        "name": event.plan.name,
        "level": event.level,
        "triggered_key": event.triggered_key,
        "message": message,
        "voice_line": voice_line,
        "voice_provider": settings.provider,
        "voice_name": voice_name,
        "occurred_at": occurred_at,
        "quote": asdict(event.quote),
        "agent_response_id": response_id,
    }
    if audio_url:
        payload["audio_url"] = audio_url
    return payload


def _audio_url(path: object) -> str:
    if not path:
        return ""
    filename = Path(str(path)).name
    return f"/api/watch/audio/{filename}" if filename else ""


def _optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except Exception:
        raise ValueError("买入价必须是数字")
    if number <= 0:
        raise ValueError("买入价必须大于 0")
    return number


def _load_seen_event_map(path: str | Path) -> dict[str, str]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    if isinstance(data, list):
        return {str(item): "" for item in data}
    return {}


def _save_seen_event_map(path: str | Path, values: dict[str, str]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    while len(values) > MAX_SEEN_EVENTS:
        values.pop(next(iter(values)))
    file_path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def _assert_port_available(host: str, port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((host, port))
    except OSError as exc:
        raise RuntimeError(f"Backend port {host}:{port} is already in use; stop the old trade_review_agent.simple_api process first") from exc
    finally:
        probe.close()


def run(host: str = "0.0.0.0", port: int = 8600) -> None:
    load_env(BASE_DIR / ".env")
    _assert_port_available(host, port)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    WATCH_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    server = SingleInstanceThreadingHTTPServer((host, port), TradeReviewHandler)
    print(f"Trade Review API listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
