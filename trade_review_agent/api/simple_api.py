from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import threading
import traceback
import csv
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from trade_review_agent.auth_system import (
    AuthError,
    admin_dashboard,
    consume_feature_credit,
    create_order,
    get_current_user,
    init_auth_db,
    login_password_user,
    login_user,
    logout_user,
    mark_order_paid,
    register_password_user,
    register_user,
    require_admin,
    require_user,
    review_feedback,
    send_email_code,
    send_login_code,
    submit_feedback,
)
from trade_review_agent.watch.alerts import AlertPlan, evaluate_plans, event_dedupe_key, load_plans, save_plans
from trade_review_agent.ocr.ai_trade_parser import TradeParsingError
from trade_review_agent.common.config import load_env
from trade_review_agent.ocr.ocr_trades import trade_file_to_trade_csv
from trade_review_agent.common.openai_agent_api import OpenAIAgentError
from trade_review_agent.market.stock_resolver import resolve_stock_code
from trade_review_agent.review.final_wang_agent.agent import FinalWangAgentError
from trade_review_agent.review.simple_wang_report import run_simple_wang_review
from trade_review_agent.watch.voice_settings import VoiceSettings, load_voice_settings, normalize_voice_settings, save_voice_settings, voice_settings_payload
from trade_review_agent.watch.watch_agent import build_watch_plan, narrate_alert_event, preview_voice_line
from trade_review_agent.watch.watch_form_ocr import extract_watch_form_from_image


BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "work" / "api_uploads"
REPORT_DIR = BASE_DIR / "outputs" / "api_reports"
CACHE_DB = BASE_DIR / "work" / "real_trade_review_cache.sqlite"
ALERT_PLANS = BASE_DIR / "work" / "alert_plans.json"
VOICE_SETTINGS_PATH = BASE_DIR / "work" / "watch_voice_settings.json"
WATCH_AUDIO_DIR = BASE_DIR / "work" / "tts"
WATCH_SEEN_EVENTS = BASE_DIR / "work" / "watch_seen_events.json"
API_ERROR_LOG = BASE_DIR / "work" / "api_errors.log"
AUTH_DB = BASE_DIR / "work" / "auth.sqlite"
CN_TZ = ZoneInfo("Asia/Shanghai")
ALLOWED_SUFFIXES = {".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
MAX_SEEN_EVENTS = 2048
REPORT_MANIFEST_NAME = "report_manifest.json"
REPORT_STATUS_NAME = "report_status.json"
RESEARCH_PRESENTER_NAME = "research_presenter_data.json"
RESEARCH_DEBUG_NAME = "research_debug_data.json"


def normalize_research_model_tier(value: object = None) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "better", "premium", "gpt55", "gpt-5.5"}:
        return "better"
    return "standard"


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
            if path == "/api/auth/me":
                self._auth_me()
                return
            if path == "/api/admin/dashboard":
                self._admin_dashboard()
                return
            if path == "/api/reports":
                self._list_reports()
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
        except AuthError as exc:
            self._json({"error": exc.message}, status=exc.status)
        except Exception as exc:
            self._send_error(exc)

    def do_POST(self) -> None:
        self._begin_request()
        path = self._request_path()
        try:
            if path == "/api/auth/register":
                self._auth_register()
                return
            if path == "/api/auth/login":
                self._auth_login()
                return
            if path == "/api/auth/send-code":
                self._auth_send_code()
                return
            if path == "/api/auth/send-email-code":
                self._auth_send_email_code()
                return
            if path == "/api/auth/password-register":
                self._auth_password_register()
                return
            if path == "/api/auth/password-login":
                self._auth_password_login()
                return
            if path == "/api/auth/logout":
                self._auth_logout()
                return
            if path == "/api/feedback":
                self._submit_feedback()
                return
            if path == "/api/orders":
                self._create_order()
                return
            if path.startswith("/api/admin/feedback/"):
                self._admin_review_feedback(path)
                return
            if path.startswith("/api/admin/orders/"):
                self._admin_mark_order(path)
                return
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
        except AuthError as exc:
            self._json({"error": exc.message}, status=exc.status)
        except ValueError as exc:
            self._send_error(exc, status=400)
        except Exception as exc:
            self._send_error(exc)

    def _create_reports(self) -> None:
        user = self._require_user()
        updated_user = consume_feature_credit(
            AUTH_DB,
            user_id=int(user["id"]),
            feature="review_report",
            ip=self._client_ip(),
        )
        self._charged_user = updated_user
        self._create_reports_resilient()

    def _list_reports(self) -> None:
        self._require_user()
        limit = 30
        query = urlparse(self.path).query
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "limit":
                try:
                    limit = max(1, min(100, int(value)))
                except ValueError:
                    limit = 30
        self._json({"reports": _recent_report_summaries(limit=limit)})

    def _auth_register(self) -> None:
        payload = self._read_json_body()
        result = register_user(
            AUTH_DB,
            phone=str(payload.get("phone") or ""),
            code=str(payload.get("code") or ""),
            password=str(payload.get("password") or ""),
            invite_code=str(payload.get("invite_code") or ""),
            ip=self._client_ip(),
        )
        self._json(result)

    def _auth_login(self) -> None:
        payload = self._read_json_body()
        result = login_user(
            AUTH_DB,
            phone=str(payload.get("phone") or ""),
            code=str(payload.get("code") or ""),
            password=str(payload.get("password") or ""),
            ip=self._client_ip(),
        )
        self._json(result)

    def _auth_password_register(self) -> None:
        payload = self._read_json_body()
        result = register_password_user(
            AUTH_DB,
            username=str(payload.get("username") or ""),
            email=str(payload.get("email") or ""),
            password=str(payload.get("password") or ""),
            email_code=str(payload.get("email_code") or payload.get("code") or ""),
            invite_code=str(payload.get("invite_code") or ""),
            ip=self._client_ip(),
        )
        self._json(result)

    def _auth_password_login(self) -> None:
        payload = self._read_json_body()
        result = login_password_user(
            AUTH_DB,
            account=str(payload.get("account") or ""),
            password=str(payload.get("password") or ""),
            ip=self._client_ip(),
        )
        self._json(result)

    def _auth_send_code(self) -> None:
        payload = self._read_json_body()
        result = send_login_code(
            AUTH_DB,
            phone=str(payload.get("phone") or ""),
            purpose=str(payload.get("purpose") or "login"),
            ip=self._client_ip(),
            log_path=BASE_DIR / "work" / "sms_codes.log",
        )
        self._json(result)

    def _auth_send_email_code(self) -> None:
        payload = self._read_json_body()
        result = send_email_code(
            AUTH_DB,
            email=str(payload.get("email") or ""),
            purpose=str(payload.get("purpose") or "register"),
            ip=self._client_ip(),
            log_path=BASE_DIR / "work" / "email_codes.log",
        )
        self._json(result)

    def _auth_logout(self) -> None:
        logout_user(AUTH_DB, self._bearer_token())
        self._json({"ok": True})

    def _auth_me(self) -> None:
        user = get_current_user(AUTH_DB, self._bearer_token())
        self._json({"user": user})

    def _submit_feedback(self) -> None:
        user = self._require_user()
        payload = self._read_json_body()
        result = submit_feedback(
            AUTH_DB,
            user_id=int(user["id"]),
            category=str(payload.get("category") or "建议"),
            content=str(payload.get("content") or ""),
            contact=str(payload.get("contact") or ""),
        )
        refreshed = get_current_user(AUTH_DB, self._bearer_token())
        self._json({"feedback": result, "user": refreshed})

    def _create_order(self) -> None:
        user = self._require_user()
        payload = self._read_json_body()
        result = create_order(
            AUTH_DB,
            user_id=int(user["id"]),
            plan_name=str(payload.get("plan_name") or "次数包"),
            credits=int(payload.get("credits") or 0),
            amount_cents=int(payload.get("amount_cents") or 0),
        )
        self._json({"order": result})

    def _admin_dashboard(self) -> None:
        self._require_admin()
        query = urlparse(self.path).query
        days = 14
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "days" and value.isdigit():
                days = int(value)
        self._json(admin_dashboard(AUTH_DB, days=days))

    def _admin_review_feedback(self, path: str) -> None:
        self._require_admin()
        parts = path.split("/")
        if len(parts) != 5:
            self._json({"error": "not found"}, status=404)
            return
        payload = self._read_json_body()
        result = review_feedback(
            AUTH_DB,
            feedback_id=int(parts[4]),
            status=str(payload.get("status") or ""),
            admin_note=str(payload.get("admin_note") or ""),
        )
        self._json({"feedback": result})

    def _admin_mark_order(self, path: str) -> None:
        self._require_admin()
        parts = path.split("/")
        if len(parts) != 6 or parts[5] != "paid":
            self._json({"error": "not found"}, status=404)
            return
        result = mark_order_paid(AUTH_DB, order_id=int(parts[4]))
        self._json({"order": result})

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
            manual_trade = _manual_trade_from_fields(fields)
            if not manual_trade and (not filename or data is None):
                self._json({"error": "missing file"}, status=400)
                return
            research_model_tier = normalize_research_model_tier(fields.get("research_model_tier") or fields.get("better_report"))

            upload_path: Path | None = None
            suffix = ""
            if not manual_trade:
                filename = Path(filename or "upload.csv").name
                suffix = Path(filename).suffix.lower()
            if not manual_trade and suffix not in ALLOWED_SUFFIXES:
                self._json({"error": "仅支持 xls/xlsx/csv/txt 成交记录文件或 png/jpg/jpeg/webp 成交截图"}, status=400)
                return

            self._set_stage("create_run")
            run_id = uuid4().hex
            run_dir = REPORT_DIR / run_id
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            if manual_trade:
                self._set_stage("write_manual_trade", run_id=run_id)
                (run_dir / "manual_trade_source.json").write_text(
                    json.dumps(manual_trade, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                self._set_stage("write_upload", run_id=run_id)
                upload_path = UPLOAD_DIR / f"{run_id}{suffix}"
                upload_path.write_bytes(data or b"")

            self._set_stage("queued", run_id=run_id)
            _write_report_status(run_id, run_dir, status="queued", stage="queued", request_id=self._request_id)
            _start_report_generation_task(
                run_id=run_id,
                run_dir=run_dir,
                upload_path=upload_path,
                manual_trade=manual_trade,
                research_model_tier=research_model_tier,
                request_id=self._request_id,
            )
            queued = _report_status_payload(run_id, status="queued", stage="queued")
            charged_user = getattr(self, "_charged_user", None)
            if charged_user:
                queued["user"] = charged_user
            self._json(queued, status=202)
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
        user = self._require_user()
        updated_user = consume_feature_credit(
            AUTH_DB,
            user_id=int(user["id"]),
            feature="watch_plan",
            ip=self._client_ip(),
        )
        self._set_stage("create_watch_plan")
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

        self._set_stage("watch_plan_agent")
        plan = build_watch_plan(
            stock_name=stock_name,
            buy_date=buy_date,
            position=position,
            buy_price=buy_price,
            cache_db=CACHE_DB,
        )
        self._set_stage("save_watch_plan")
        plans = [item for item in load_plans(ALERT_PLANS) if item.plan_id != plan.plan_id]
        plans.insert(0, plan)
        save_plans(ALERT_PLANS, plans)
        self._json({"plan": _plan_payload(plan), "plans": [_plan_payload(item) for item in plans], "user": updated_user})

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
        content_type = _content_type_with_charset(file_path.name)
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
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _begin_request(self) -> None:
        self._request_id = uuid4().hex
        self._run_id = ""
        self._stage = "route"

    def _set_stage(self, stage: str, *, run_id: str | None = None) -> None:
        self._stage = stage
        if run_id is not None:
            self._run_id = run_id

    def _bearer_token(self) -> str:
        value = self.headers.get("authorization", "").strip()
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return ""

    def _require_user(self) -> dict:
        return require_user(AUTH_DB, self._bearer_token())

    def _require_admin(self) -> dict:
        return require_admin(AUTH_DB, self._bearer_token())

    def _client_ip(self) -> str:
        forwarded = self.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
        return self.client_address[0] if self.client_address else ""

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


def _content_type_with_charset(filename: str) -> str:
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if content_type in {"text/html", "text/plain", "text/csv", "application/json", "application/javascript"}:
        return f"{content_type}; charset=utf-8"
    return content_type



def _manual_trade_from_fields(fields: dict[str, str]) -> dict | None:
    enabled = str(fields.get("manual_trade") or "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None

    stock_name = str(fields.get("manual_stock_name") or "").strip()
    stock_code = "".join(ch for ch in str(fields.get("manual_stock_code") or "") if ch.isdigit())
    trade_at = str(fields.get("manual_trade_at") or "").strip()
    side = _manual_side(fields.get("manual_side"))
    position = str(fields.get("manual_position") or "").strip()
    price = _optional_float(fields.get("manual_price"))

    if not stock_name:
        raise ValueError("请填写股票名字")
    if not stock_code:
        stock_code = resolve_stock_code(stock_name, allow_fetch=False)
    if not trade_at:
        raise ValueError("请选择交易时间")

    if price is None:
        raise ValueError("请填写买入价格")

    trade_date, trade_time = _manual_trade_datetime(trade_at)
    stock_code = stock_code.zfill(6)[-6:] if stock_code else ""
    return {
        "trade_date": trade_date,
        "trade_time": trade_time,
        "code": stock_code,
        "name": stock_name,
        "side": side,
        "price": price,
        "fee": 0.0,
        "market": "A-share",
        "source_text": f"manual input; name={stock_name}; code={stock_code or 'not resolved'}; price={price}",
        "position": position,
    }


def _manual_side(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"sell", "s"} or "卖" in text:
        return "sell"
    return "buy"


def _manual_trade_datetime(value: str) -> tuple[str, str]:
    normalized = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M:%S")
        except ValueError:
            continue
    raise ValueError("交易时间格式不正确")


def _manual_position_quantity(position: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", position.replace(",", ""))
    if not match:
        return 1.0
    value = float(match.group(0))
    return value if value > 0 else 1.0


def _write_manual_trade_csv(manual_trade: dict, output_csv: Path) -> Path:
    columns = [
        "trade_date",
        "trade_time",
        "code",
        "name",
        "side",
        "price",
        "fee",
        "market",
        "source_text",
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({column: manual_trade.get(column, "") for column in columns})
    return output_csv


def _start_report_generation_task(
    *,
    run_id: str,
    run_dir: Path,
    upload_path: Path | None,
    manual_trade: dict | None,
    research_model_tier: str,
    request_id: str,
) -> None:
    thread = threading.Thread(
        target=_run_report_generation_task,
        kwargs={
            "run_id": run_id,
            "run_dir": run_dir,
            "upload_path": upload_path,
            "manual_trade": manual_trade,
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
    upload_path: Path | None,
    manual_trade: dict | None,
    research_model_tier: str,
    request_id: str,
) -> None:
    stage = "queued"
    try:
        stage = "manual_trade_file" if manual_trade else "ocr_trade_file"
        _write_report_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        trades_path = run_dir / "ai_trades.csv"
        if manual_trade:
            _write_manual_trade_csv(manual_trade, trades_path)
        else:
            if upload_path is None:
                raise ValueError("missing upload file")
            trade_file_to_trade_csv(upload_path, trades_path)

        stage = "build_ai_review"
        _write_report_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        results = run_simple_wang_review(
            trades_path=trades_path,
            output_dir=run_dir,
            requested_research_model_tier=research_model_tier,
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
        "research_debug_url": f"/api/reports/{run_id}/{RESEARCH_DEBUG_NAME}",
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
    manifest = _manifest_from_run_dir(run_id, run_dir)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not isinstance(manifest, dict) or not manifest.get("reports"):
        return None
    return manifest


def _api_error_payload(exc: Exception, *, request_id: str, run_id: str = "", stage: str = "") -> dict:
    if isinstance(exc, TradeParsingError):
        payload = {
            "error": exc.user_message,
            "detail": _trade_parsing_error_detail(exc),
            "code": exc.code,
            "retryable": exc.retryable,
            "request_id": request_id,
            "run_id": run_id,
            "stage": stage,
        }
        if exc.retry_after is not None:
            payload["retry_after"] = exc.retry_after
        return payload
    if isinstance(exc, OpenAIAgentError):
        return {
            "error": exc.user_message,
            "detail": _openai_agent_error_detail(exc),
            "code": exc.code,
            "retryable": exc.retryable,
            "request_id": request_id,
            "run_id": run_id,
            "stage": stage,
        }
    if isinstance(exc, FinalWangAgentError):
        return {
            "error": exc.user_message,
            "detail": _redact_sensitive(exc.detail),
            "code": exc.code,
            "retryable": exc.retryable,
            "request_id": request_id,
            "run_id": run_id,
            "stage": stage,
        }
    return {
        "error": "Internal Server Error",
        "detail": _redact_sensitive(str(exc)),
        "request_id": request_id,
        "run_id": run_id,
        "stage": stage,
    }


def _api_error_status(exc: Exception, fallback: int = 500) -> int:
    if isinstance(exc, TradeParsingError):
        if exc.status_code == 429:
            return 429
        if exc.status_code in {400, 401, 403, 404}:
            return 502
        if exc.status_code and 500 <= exc.status_code <= 599:
            return 503
        return 503 if exc.retryable else 502
    if isinstance(exc, OpenAIAgentError):
        if exc.status_code == 429:
            return 429
        if exc.status_code in {400, 401, 403, 404}:
            return 502
        if exc.status_code and 500 <= exc.status_code <= 599:
            return 503
        return 503 if exc.retryable else 502
    if isinstance(exc, FinalWangAgentError):
        if exc.status_code == 429:
            return 429
        if exc.status_code in {400, 401, 403, 404}:
            return 502
        if exc.status_code and 500 <= exc.status_code <= 599:
            return 503
        return 503 if exc.retryable else 502
    return fallback


def _trade_parsing_error_detail(exc: TradeParsingError) -> str:
    if exc.status_code == 429:
        return "DeepSeek 识别请求过于频繁，已重试后仍被限流"
    if exc.status_code in {500, 502, 503, 504}:
        return f"DeepSeek 识别服务临时异常（HTTP {exc.status_code}），已重试后仍失败"
    if exc.status_code:
        return f"DeepSeek 识别请求失败（HTTP {exc.status_code}）"
    return "DeepSeek 识别请求失败"


def _openai_agent_error_detail(exc: OpenAIAgentError) -> str:
    if exc.status_code == 429:
        return "OpenAI 请求过于频繁，已重试后仍被限流"
    if exc.status_code in {500, 502, 503, 504}:
        return f"OpenAI 服务临时异常（HTTP {exc.status_code}），请稍后重试"
    if exc.status_code:
        return f"OpenAI 请求失败（HTTP {exc.status_code}）"
    return "OpenAI 请求失败"


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
            "exception": _redact_sensitive(repr(exc)),
            "traceback": _redact_sensitive(traceback.format_exc()),
        }
        with API_ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        print(f"[warn] failed to write API error log for {request_id}", flush=True)


def _redact_sensitive(text: str) -> str:
    redacted = str(text or "")
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_PROXY_URL"):
        value = os.getenv(key, "")
        if value:
            redacted = redacted.replace(value, "<redacted>")
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", redacted)
    redacted = re.sub(r"sk-[A-Za-z0-9._~+/=-]+", "<redacted>", redacted)
    return redacted


def _resolve_report_file(run_id: str, run_dir: Path, filename: str) -> Path:
    report_path = run_dir / filename
    if filename == RESEARCH_PRESENTER_NAME:
        if report_path.exists() and _is_legacy_presenter(report_path):
            report_path.unlink(missing_ok=True)
        _copy_first_artifact_if_missing(run_dir, RESEARCH_PRESENTER_NAME, "*.presenter.json")
        if not report_path.exists() and run_dir.exists() and run_dir.is_dir():
            _write_legacy_presenter_if_missing(run_id, run_dir, report_path)
        return report_path if report_path.exists() else (_first_report_artifact(run_dir, "*.presenter.json") or report_path)
    if report_path.exists() and report_path.is_file():
        return report_path
    if not run_dir.exists() or not run_dir.is_dir():
        return report_path

    if filename == RESEARCH_DEBUG_NAME:
        _copy_first_artifact_if_missing(run_dir, RESEARCH_DEBUG_NAME, "*.debug.json")
        return report_path if report_path.exists() else (_first_report_artifact(run_dir, "*.debug.json") or report_path)
    if filename == REPORT_MANIFEST_NAME:
        _ensure_report_aliases(run_dir)
        manifest_path = run_dir / REPORT_MANIFEST_NAME
        manifest = _manifest_from_run_dir(run_id, run_dir)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path
    return report_path


def _ensure_report_aliases(run_dir: Path) -> None:
    _copy_first_artifact_if_missing(run_dir, RESEARCH_PRESENTER_NAME, "*.presenter.json")
    _copy_first_artifact_if_missing(run_dir, RESEARCH_DEBUG_NAME, "*.debug.json")


def _copy_first_artifact_if_missing(run_dir: Path, alias_name: str, pattern: str) -> None:
    alias_path = run_dir / alias_name
    if alias_path.exists():
        return
    source = _first_report_artifact(run_dir, pattern)
    if source:
        alias_path.write_bytes(source.read_bytes())


def _is_legacy_presenter(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("presenter_contract") == "legacy_html_adapter_v1"


def _write_legacy_presenter_if_missing(run_id: str, run_dir: Path, output_path: Path) -> None:
    html_path = _first_report_artifact(run_dir, "*.html")
    if not html_path or html_path.name == "index.html":
        return
    try:
        html_text = html_path.read_text(encoding="utf-8")
    except Exception:
        return
    presenter = _legacy_html_presenter(run_id, html_text)
    output_path.write_text(json.dumps(presenter, ensure_ascii=False, indent=2), encoding="utf-8")


def _legacy_html_presenter(run_id: str, html_text: str) -> dict:
    title = _strip_html(_first_match(html_text, r"<h1[^>]*>(.*?)</h1>")) or _report_title_from_stem(run_id)
    summary = _strip_html(_first_match(html_text, r'<p class="summary-text">(.*?)</p>')) or "原始报告已生成复盘结论，请结合交易逻辑、题材分析和同行对比查看。"
    score = _safe_int(_strip_html(_first_match(html_text, r'<div class="score-main">(.*?)</div>')))
    rating = _strip_html(_first_match(html_text, r'<div class="rating">(.*?)</div>'))
    sections = _legacy_sections(html_text)
    conclusion = _pick_section(sections, "AI 复盘结论") or summary
    route = _pick_section(sections, "最佳交易路线对比")
    exam = _pick_section(sections, "交易体检")
    chain = _pick_section(sections, "产业链与个股定位")
    emotion = _pick_section(sections, "市场情绪与行为显微镜")
    advice = _pick_section(sections, "AI 教练总结与建议")
    market = _pick_section(sections, "大盘、板块与个股共振")
    logic_text = "\n\n".join(part for part in [conclusion, route, exam] if part).strip()
    theme_text = "\n\n".join(part for part in [chain, emotion, market] if part).strip()
    peer_items = _legacy_peer_items(html_text)
    return {
        "presenter_contract": "legacy_html_adapter_v1",
        "review": {
            "verdict": {"text": summary},
            "scores": {"items": [{"key": "total", "label": "综合评分", "value": score}]},
            "judgments": {"items": []},
            "items": [
                {"key": "legacyConclusion", "label": "AI 复盘结论", "text": conclusion},
                {"key": "legacyRoute", "label": "最佳交易路线", "text": route or "原始报告未提供最佳路线对比。"},
                {"key": "legacyExam", "label": "交易体检", "text": exam or "原始报告未提供交易体检。"},
                {"key": "legacyRating", "label": "交易评级", "text": rating or "原始报告未提供交易评级。"},
            ],
            "nextActions": {
                "text": advice or "原始报告未提供 AI 教练建议。",
                "items": [{"text": advice}] if advice else [],
            },
        },
        "bestChoice": {"available": bool(peer_items), "name": peer_items[0]["name"] if peer_items else None, "summary": None, "ranking": peer_items},
        "companyComparison": {"shortTermCapitalRanking": peer_items, "industryValueRanking": [], "summary": ""},
        "tradeLogic": {"summary": "交易逻辑", "text": logic_text or summary},
        "themeAnalysis": {
            "industryChain": {"nodes": _legacy_chain_nodes(chain)},
            "profitFlow": {"text": theme_text or "原始报告未提供题材分析。"},
        },
    }


def _legacy_sections(html_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for raw_title, raw_body in re.findall(r'<h2 class="section-title">.*?</span>(.*?)</h2>(.*?)(?=<h2 class="section-title">|</section>|<footer)', html_text, flags=re.S):
        title = _strip_html(raw_title)
        body = _strip_html(raw_body)
        if title and body:
            sections[title] = body
    return sections


def _legacy_peer_items(html_text: str) -> list[dict]:
    if not any(keyword in html_text for keyword in ("同行对比", "相关公司比较", "公司比较", "同行标的")):
        return []
    rows = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", html_text, flags=re.S)
    items = []
    for index, row in enumerate(rows[:6], start=1):
        name = _strip_html(row[0])
        reason = " / ".join(_strip_html(value) for value in row[1:] if _strip_html(value))
        if name:
            items.append({"rank": index, "name": name, "reason": reason})
    if items:
        return items
    tags = [_strip_html(value) for value in re.findall(r'<div class="tag">(.*?)</div>|<span class="tag">(.*?)</span>', html_text, flags=re.S) for value in value if value]
    return [{"rank": index + 1, "name": tag, "reason": "原始报告标签"} for index, tag in enumerate(tags[:6])]


def _legacy_chain_nodes(text: str) -> list[dict]:
    if not text:
        return []
    names = [_strip_html(value) for value in re.findall(r"<b>(.*?)</b>", text, flags=re.S)]
    if not names:
        names = [part.strip() for part in re.split(r"[→\n]+", text) if part.strip()]
    return [{"name": name, "current": index == 1} for index, name in enumerate(names[:6])]


def _pick_section(sections: dict[str, str], key: str) -> str:
    for title, body in sections.items():
        if key in title:
            return body
    return ""


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.S)
    return match.group(1) if match else ""


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    text = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _safe_int(value: str) -> int:
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def _first_report_artifact(run_dir: Path, pattern: str) -> Path | None:
    matches = sorted(path for path in run_dir.glob(pattern) if path.is_file())
    return matches[0] if matches else None


def _manifest_from_run_dir(run_id: str, run_dir: Path) -> dict:
    reports = []
    html_files = sorted(path for path in run_dir.glob("*.html") if path.is_file() and path.name != "index.html")
    for html_path in html_files:
        debug_path = html_path.with_suffix(".debug.json")
        presenter_path = html_path.with_suffix(".presenter.json")
        metadata = _report_metadata_from_debug(debug_path)
        html_url = f"/api/reports/{run_id}/{html_path.name}"
        debug_url = f"/api/reports/{run_id}/{debug_path.name}" if debug_path.exists() else ""
        presenter_url = f"/api/reports/{run_id}/{presenter_path.name}" if presenter_path.exists() else ""
        if not debug_url and (run_dir / RESEARCH_DEBUG_NAME).exists():
            debug_url = f"/api/reports/{run_id}/{RESEARCH_DEBUG_NAME}"
        if not presenter_url and (run_dir / RESEARCH_PRESENTER_NAME).exists():
            presenter_url = f"/api/reports/{run_id}/{RESEARCH_PRESENTER_NAME}"
        reports.append(
            {
                "title": _report_title_from_stem(html_path.stem),
                "rating": "",
                "score": 0,
                "trade_type": "",
                "requested_research_model_tier": metadata["requested_tier"],
                "research_model_tier": metadata["tier"],
                "actual_research_model_tier": metadata["tier"],
                "wang_model": metadata["wang_model"],
                "url": html_url,
                "html_url": html_url,
                "debug_url": debug_url,
                "presenter_url": presenter_url,
            }
        )
    return _manifest_payload(run_id, reports)


def _report_metadata_from_debug(path: Path) -> dict[str, str]:
    fallback = {"requested_tier": "standard", "tier": "standard", "wang_model": "final_wang_agent"}
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
    }


def _report_title_from_stem(stem: str) -> str:
    parts = stem.split("_")
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return stem


def _report_manifest(run_id: str, results: list) -> dict:
    reports = []
    for result in results:
        html_url = f"/api/reports/{run_id}/{result.output.name}"
        debug_url = f"/api/reports/{run_id}/{result.output.with_suffix('.debug.json').name}"
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
                "url": html_url,
                "html_url": html_url,
                "debug_url": debug_url,
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
        "debug_url": first.get("debug_url", ""),
        "requested_research_model_tier": first.get("requested_research_model_tier", first.get("research_model_tier", "standard")),
        "research_model_tier": first.get("research_model_tier", "standard"),
        "actual_research_model_tier": first.get("actual_research_model_tier", first.get("research_model_tier", "standard")),
        "wang_model": first.get("wang_model", "final_wang_agent"),
        "research_debug_url": f"/api/reports/{run_id}/{RESEARCH_DEBUG_NAME}",
        "research_presenter_url": f"/api/reports/{run_id}/{RESEARCH_PRESENTER_NAME}",
    }


def _recent_report_summaries(*, limit: int = 30) -> list[dict]:
    if not REPORT_DIR.exists():
        return []
    items: list[dict] = []
    for run_dir in REPORT_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        manifest = _recover_report_manifest(run_dir.name, run_dir)
        if not manifest:
            continue
        first = (manifest.get("reports") or [{}])[0]
        try:
            updated_at = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            updated_at = ""
        items.append(
            {
                "run_id": run_dir.name,
                "title": _recent_report_title(run_dir, first),
                "rating": first.get("rating") or "",
                "score": first.get("score") or 0,
                "status": "done",
                "created_at": updated_at,
                "report_route": f"/review/report/{run_dir.name}",
                "html_url": manifest.get("html_url") or first.get("html_url") or "",
                "presenter_url": manifest.get("presenter_url") or first.get("presenter_url") or "",
                "has_presenter": bool(manifest.get("presenter_url") or first.get("presenter_url")),
                "research_model_tier": manifest.get("research_model_tier") or first.get("research_model_tier") or "standard",
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def _recent_report_title(run_dir: Path, first: dict) -> str:
    trade = _recent_report_trade_info(run_dir)
    if trade:
        name = trade.get("name") or trade.get("code") or "未知股票"
        side = _trade_side_label(trade.get("side"))
        trade_at = " ".join(part for part in [trade.get("trade_date"), trade.get("trade_time")] if part).strip()
        return " - ".join(part for part in [str(name), side, trade_at] if part)
    return str(first.get("title") or _report_title_from_stem(run_dir.name))


def _recent_report_trade_info(run_dir: Path) -> dict[str, str]:
    manual_path = run_dir / "manual_trade_source.json"
    if manual_path.exists():
        try:
            data = json.loads(manual_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items() if value is not None}

    csv_path = run_dir / "ai_trades.csv"
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle), None)
        except Exception:
            row = None
        if isinstance(row, dict):
            return {str(key): str(value) for key, value in row.items() if value is not None}
    return {}


def _trade_side_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"sell", "s"} or "卖" in text:
        return "卖出"
    if text in {"buy", "b"} or "买" in text:
        return "买入"
    return text


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
        raise RuntimeError(f"Backend port {host}:{port} is already in use; stop the old trade_review_agent.api.simple_api process first") from exc
    finally:
        probe.close()


def run(host: str = "0.0.0.0", port: int = 8600) -> None:
    load_env(BASE_DIR / ".env")
    _assert_port_available(host, port)
    init_auth_db(AUTH_DB)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    WATCH_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    server = SingleInstanceThreadingHTTPServer((host, port), TradeReviewHandler)
    print(f"Trade Review API listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
