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
from trade_review_agent.review.market_day_agent.agent import MarketDayAgentError, normalize_market_date, run_market_day_agent
from trade_review_agent.review.simple_wang_report import run_simple_wang_review
from trade_review_agent.watch.voice_settings import VoiceSettings, load_voice_settings, normalize_voice_settings, save_voice_settings, voice_settings_payload
from trade_review_agent.watch.watch_agent import build_watch_plan, narrate_alert_event, preview_voice_line
from trade_review_agent.watch.watch_form_ocr import extract_watch_form_from_image


BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "work" / "api_uploads"
REPORT_DIR = BASE_DIR / "outputs" / "api_reports"
MARKET_DAY_REPORT_DIR = BASE_DIR / "outputs" / "market_day_reports"
CACHE_DB = BASE_DIR / "work" / "real_trade_review_cache.sqlite"
ALERT_PLANS = BASE_DIR / "work" / "alert_plans.json"
VOICE_SETTINGS_PATH = BASE_DIR / "work" / "watch_voice_settings.json"
WATCH_AUDIO_DIR = BASE_DIR / "work" / "tts"
WATCH_SEEN_EVENTS = BASE_DIR / "work" / "watch_seen_events.json"
WEBHOOK_EVENTS_PATH = BASE_DIR / "work" / "webhook_events.jsonl"
AUCTION_STRENGTH_PATH = BASE_DIR / "work" / "auction_strength_reports.jsonl"
AUCTION_STRENGTH_V2_PATH = BASE_DIR / "work" / "auction_strength_v2_reports.jsonl"
API_ERROR_LOG = BASE_DIR / "work" / "api_errors.log"
AUTH_DB = BASE_DIR / "work" / "auth.sqlite"
CN_TZ = ZoneInfo("Asia/Shanghai")
ALLOWED_SUFFIXES = {".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
MAX_SEEN_EVENTS = 2048
REPORT_MANIFEST_NAME = "report_manifest.json"
REPORT_STATUS_NAME = "report_status.json"
RESEARCH_PRESENTER_NAME = "research_presenter_data.json"
RESEARCH_DEBUG_NAME = "research_debug_data.json"
MARKET_DAY_REPORT_NAME = "market_day_report.json"


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
            if path == "/api/market-day/reports":
                self._list_market_day_reports()
                return
            if path == "/api/webhooks":
                self._list_webhooks()
                return
            if path == "/api/auction-strength":
                self._list_auction_strength_reports()
                return
            if path == "/api/auction-strength-v2":
                self._list_auction_strength_v2_reports()
                return
            if path.startswith("/api/market-day/reports/"):
                self._serve_market_day_report(path)
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
            if path == "/api/market-day/reports":
                self._create_market_day_report()
                return
            if path == "/api/webhooks":
                self._receive_webhook()
                return
            if path == "/api/auction-strength":
                self._receive_auction_strength_report()
                return
            if path == "/api/auction-strength-v2":
                self._receive_auction_strength_v2_report()
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

    def _create_market_day_report(self) -> None:
        user = self._require_user()
        payload = self._read_json_body()
        market_date = normalize_market_date(str(payload.get("market_date") or "").strip() or None)
        run_id = f"{market_date.replace('-', '')}_{datetime.now(CN_TZ).strftime('%H%M%S')}_{uuid4().hex[:6]}"
        run_dir = MARKET_DAY_REPORT_DIR / run_id
        updated_user = consume_feature_credit(
            AUTH_DB,
            user_id=int(user["id"]),
            feature="market_day_report",
            ip=self._client_ip(),
            related_id=run_id,
        )
        self._charged_user = updated_user
        request_id = getattr(self, "_request_id", "") or uuid4().hex
        _write_market_day_status(run_id, run_dir, status="queued", stage="queued", request_id=request_id)
        _start_market_day_generation_task(
            run_id=run_id,
            run_dir=run_dir,
            market_date=market_date,
            request_id=request_id,
        )
        response = _market_day_status_payload(run_id, status="queued", stage="queued", request_id=request_id)
        response["market_date"] = market_date
        response["user"] = updated_user
        self._json(response, status=202)

    def _list_market_day_reports(self) -> None:
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
        self._json({"reports": _recent_market_day_report_summaries(limit=limit)})

    def _list_webhooks(self) -> None:
        limit = 30
        query = urlparse(self.path).query
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "limit":
                try:
                    limit = max(1, min(200, int(value)))
                except ValueError:
                    limit = 30
        events = _recent_webhook_events(WEBHOOK_EVENTS_PATH, limit=limit)
        self._json({"events": events, "count": len(events), "total": _webhook_event_count(WEBHOOK_EVENTS_PATH)})

    def _receive_webhook(self) -> None:
        _assert_webhook_secret(
            expected=os.getenv("WEBHOOK_SECRET", ""),
            header_value=self.headers.get("x-webhook-secret", ""),
            query=urlparse(self.path).query,
        )
        event = _webhook_event_from_request(
            payload=self._read_webhook_payload(),
            headers={key.lower(): value for key, value in self.headers.items()},
            source_ip=self._client_ip(),
            request_id=getattr(self, "_request_id", ""),
        )
        _append_webhook_event(WEBHOOK_EVENTS_PATH, event)
        self._json({"ok": True, "event": _webhook_public_event(event)}, status=202)

    def _list_auction_strength_reports(self) -> None:
        self._list_auction_strength_reports_from_path(AUCTION_STRENGTH_PATH, include_v2=False)

    def _list_auction_strength_v2_reports(self) -> None:
        self._list_auction_strength_reports_from_path(AUCTION_STRENGTH_V2_PATH, include_v2=True)

    def _list_auction_strength_reports_from_path(self, report_path: Path, *, include_v2: bool) -> None:
        limit = 20
        trade_date = ""
        query = urlparse(self.path).query
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "limit":
                try:
                    limit = max(1, min(100, int(value)))
                except ValueError:
                    limit = 20
            if key == "date":
                raw_trade_date = unquote(value).strip()
                if raw_trade_date:
                    try:
                        trade_date = normalize_market_date(raw_trade_date)
                    except ValueError:
                        self._json({"error": "invalid date, expected YYYY-MM-DD"}, status=400)
                        return
        reports = _recent_auction_strength_reports(report_path, limit=limit, trade_date=trade_date, include_v2=include_v2)
        total = _auction_strength_report_count(report_path, trade_date=trade_date)
        self._json({"latest": reports[0] if reports else None, "reports": reports, "count": len(reports), "total": total})

    def _receive_auction_strength_report(self) -> None:
        self._receive_auction_strength_report_to_path(AUCTION_STRENGTH_PATH, include_v2=False)

    def _receive_auction_strength_v2_report(self) -> None:
        self._receive_auction_strength_report_to_path(AUCTION_STRENGTH_V2_PATH, include_v2=True)

    def _receive_auction_strength_report_to_path(self, report_path: Path, *, include_v2: bool) -> None:
        _assert_webhook_secret(
            expected=os.getenv("AUCTION_STRENGTH_SECRET", os.getenv("WEBHOOK_SECRET", "")),
            header_value=self.headers.get("x-auction-strength-secret", "") or self.headers.get("x-webhook-secret", ""),
            query=urlparse(self.path).query,
        )
        payload = self._read_json_body()
        report = _auction_strength_report_from_payload(
            payload=payload,
            source_ip=self._client_ip(),
            request_id=getattr(self, "_request_id", ""),
            include_v2=include_v2,
        )
        _append_webhook_event(report_path, report)
        self._json({"ok": True, "report": _auction_strength_public_report(report, include_v2=include_v2)}, status=202)

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

    def _read_webhook_payload(self) -> object:
        content_length = int(self.headers.get("content-length", "0") or 0)
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw.strip():
            return {}
        content_type = self.headers.get("content-type", "")
        text = raw.decode("utf-8", errors="replace")
        if "application/json" in content_type or text.strip().startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid webhook JSON body") from exc
        return {"raw_text": text}

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
        if _is_presenter_report_file(report_path):
            _normalize_presenter_score_file(report_path)
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

    def _serve_market_day_report(self, path: str) -> None:
        parts = path.split("/")
        if len(parts) != 6:
            self._json({"error": "not found"}, status=404)
            return
        run_id = parts[4]
        filename = Path(unquote(parts[5])).name
        run_dir = MARKET_DAY_REPORT_DIR / run_id
        if filename == "status":
            self._serve_market_day_status(run_id, run_dir)
            return
        report_path = run_dir / filename
        if filename != MARKET_DAY_REPORT_NAME or not report_path.exists() or not report_path.is_file():
            self._json({"error": "market day report not found"}, status=404)
            return
        self._serve_file(report_path)

    def _serve_market_day_status(self, run_id: str, run_dir: Path) -> None:
        report_path = run_dir / MARKET_DAY_REPORT_NAME
        if report_path.exists():
            payload = _market_day_status_payload(run_id, status="done", stage="done")
            payload["report"] = _read_json_file(report_path)
            self._json(payload)
            return
        status_path = run_dir / REPORT_STATUS_NAME
        if not status_path.exists():
            self._json(_market_day_status_payload(run_id, status="queued", stage="queued"))
            return
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._json(_api_error_payload(exc, request_id=getattr(self, "_request_id", ""), run_id=run_id, stage="read_market_day_status"), status=500)
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret, X-Auction-Strength-Secret")

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


def _start_market_day_generation_task(
    *,
    run_id: str,
    run_dir: Path,
    market_date: str,
    request_id: str,
) -> None:
    thread = threading.Thread(
        target=_run_market_day_generation_task,
        kwargs={
            "run_id": run_id,
            "run_dir": run_dir,
            "market_date": market_date,
            "request_id": request_id,
        },
        daemon=True,
        name=f"market-day-{run_id[:8]}",
    )
    thread.start()


def _run_market_day_generation_task(
    *,
    run_id: str,
    run_dir: Path,
    market_date: str,
    request_id: str,
) -> None:
    stage = "queued"
    try:
        stage = "market_day_agent"
        _write_market_day_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        report = run_market_day_agent(market_date)
        report["run_id"] = run_id
        report["status_url"] = f"/api/market-day/reports/{run_id}/status"
        report["report_url"] = f"/api/market-day/reports/{run_id}/{MARKET_DAY_REPORT_NAME}"

        stage = "write_market_day_report"
        _write_market_day_status(run_id, run_dir, status="running", stage=stage, request_id=request_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / MARKET_DAY_REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        done = _market_day_status_payload(run_id, status="done", stage="done", request_id=request_id)
        done["market_date"] = market_date
        done["report"] = report
        _write_market_day_status_payload(run_dir, done)
    except Exception as exc:
        payload = _market_day_status_payload(run_id, status="error", stage=stage, request_id=request_id)
        payload.update(_api_error_payload(exc, request_id=request_id, run_id=run_id, stage=stage))
        payload["status"] = "error"
        _write_market_day_status_payload(run_dir, payload)
        _write_api_error(
            request_id=request_id,
            method="BACKGROUND",
            path=f"/api/market-day/reports/{run_id}",
            run_id=run_id,
            stage=stage,
            exc=exc,
            recovered=False,
        )


def _market_day_status_payload(run_id: str, *, status: str, stage: str, request_id: str = "") -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "status_url": f"/api/market-day/reports/{run_id}/status",
        "report_url": f"/api/market-day/reports/{run_id}/{MARKET_DAY_REPORT_NAME}",
        "request_id": request_id,
    }


def _write_market_day_status(run_id: str, run_dir: Path, *, status: str, stage: str, request_id: str = "") -> None:
    _write_market_day_status_payload(run_dir, _market_day_status_payload(run_id, status=status, stage=stage, request_id=request_id))


def _write_market_day_status_payload(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / REPORT_STATUS_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    if isinstance(exc, MarketDayAgentError):
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


def _is_presenter_report_file(path: Path) -> bool:
    return path.name == RESEARCH_PRESENTER_NAME or path.name.endswith(".presenter.json")


def _normalize_presenter_score_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    items = (((payload.get("review") or {}).get("scores") or {}).get("items") or [])
    if not isinstance(items, list):
        return
    use_hundred_scale = any(
        (score := _raw_numeric_score(item.get("value"))) is not None and score > 10
        for item in items
        if isinstance(item, dict)
    )
    changed = False
    for item in items:
        if not isinstance(item, dict) or "value" not in item:
            continue
        normalized = _normalize_ten_point_score(item.get("value"), force_hundred_scale=use_hundred_scale)
        if normalized is None or normalized == item.get("value"):
            continue
        item["value"] = normalized
        changed = True
    if changed:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _raw_numeric_score(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    elif isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if not match:
            return None
        return float(match.group(0))
    return None


def _normalize_ten_point_score(value, *, force_hundred_scale: bool = False) -> float | int | None:
    score = _raw_numeric_score(value)
    if score is None:
        return None
    if force_hundred_scale or score > 10:
        score = score / 10
    score = max(0.0, min(10.0, score))
    rounded = round(score, 1)
    return int(rounded) if rounded.is_integer() else rounded


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


def _recent_market_day_report_summaries(*, limit: int = 30) -> list[dict]:
    if not MARKET_DAY_REPORT_DIR.exists():
        return []
    items: list[dict] = []
    for run_dir in MARKET_DAY_REPORT_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        report_path = run_dir / MARKET_DAY_REPORT_NAME
        if not report_path.exists():
            continue
        report = _read_json_file(report_path)
        market_date = str(report.get("market_date") or (report.get("report") or {}).get("marketDate") or "")
        report_body = report.get("report") if isinstance(report.get("report"), dict) else {}
        mainline = report_body.get("mainline") if isinstance(report_body.get("mainline"), dict) else {}
        try:
            updated_at = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            updated_at = ""
        items.append(
            {
                "run_id": run_dir.name,
                "title": f"{market_date or run_dir.name} AI当日行情",
                "status": "done",
                "created_at": updated_at,
                "market_date": market_date,
                "mainline": str(mainline.get("name") or ""),
                "one_line_conclusion": str(report_body.get("oneLineConclusion") or ""),
                "report_route": f"/market-day/report/{run_dir.name}",
                "report_url": f"/api/market-day/reports/{run_dir.name}/{MARKET_DAY_REPORT_NAME}",
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def _auction_strength_report_from_payload(*, payload: dict, source_ip: str, request_id: str, include_v2: bool = True) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("auction strength payload must be a JSON object")
    trade_date = str(payload.get("trade_date") or "").strip()
    analysis_time = str(payload.get("analysis_time") or "").strip()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    conclusion = payload.get("global_conclusion") if isinstance(payload.get("global_conclusion"), dict) else {}
    strong_stocks = _auction_stock_items(payload.get("top5_strong_stocks"), mode="strong")
    avoid_stocks = _auction_stock_items(payload.get("top5_avoid_stocks"), mode="avoid")
    report = {
        "id": uuid4().hex,
        "request_id": request_id,
        "received_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "source_ip": source_ip,
        "trade_date": trade_date,
        "analysis_time": analysis_time,
        "summary": {
            "one_sentence": _short_text(summary.get("one_sentence") if isinstance(summary, dict) else "", 500),
            "selection_logic": _short_text(summary.get("selection_logic") if isinstance(summary, dict) else "", 800),
            "data_limit": _short_text(summary.get("data_limit") if isinstance(summary, dict) else "", 800),
        },
        "top5_strong_stocks": strong_stocks,
        "top5_avoid_stocks": avoid_stocks,
        "global_conclusion": {
            "strongest_stock_at_925": _short_text(conclusion.get("strongest_stock_at_925") if isinstance(conclusion, dict) else "", 80),
            "strongest_theme_cluster": _short_text(conclusion.get("strongest_theme_cluster") if isinstance(conclusion, dict) else "", 120),
            "most_over_expected_stock": _short_text(conclusion.get("most_over_expected_stock") if isinstance(conclusion, dict) else "", 80),
            "best_capacity_confirmation": _short_text(conclusion.get("best_capacity_confirmation") if isinstance(conclusion, dict) else "", 80),
            "biggest_negative_feedback": _short_text(conclusion.get("biggest_negative_feedback") if isinstance(conclusion, dict) else "", 80),
            "one_sentence_for_930": _short_text(conclusion.get("one_sentence_for_930") if isinstance(conclusion, dict) else "", 500),
        },
    }
    if include_v2:
        report["global_conclusion"]["limit_open_emotion_anchors"] = _safe_auction_list(
            conclusion.get("limit_open_emotion_anchors") if isinstance(conclusion, dict) else [],
            limit=30,
        )
        report.update(
            {
                "theme_gate_result": _safe_auction_json(payload.get("theme_gate_result"), limit=100),
                "emotion_anchors": _safe_auction_list(payload.get("emotion_anchors"), limit=30),
                "timings": _auction_timings(payload),
                "quote_provider": _short_text(payload.get("quote_provider"), 80),
                "source_csv": _short_text(payload.get("source_csv"), 300),
                "data_limit": _safe_text_list(payload.get("data_limit"), limit=30, item_limit=300),
                "warnings": _safe_text_list(payload.get("warnings"), limit=20, item_limit=300),
                "raw_payload": payload,
            }
        )
    return report


def _auction_stock_items(value: object, *, mode: str) -> list[dict]:
    if not isinstance(value, list):
        return []
    items: list[dict] = []
    for index, raw_item in enumerate(value[:20], start=1):
        if not isinstance(raw_item, dict):
            continue
        follow_key = "observe_after_930" if mode == "strong" else "risk_after_930"
        items.append(
            {
                "rank": _safe_rank(raw_item.get("rank"), fallback=index),
                "code": _short_text(raw_item.get("code"), 16),
                "name": _short_text(raw_item.get("name"), 80),
                "theme": _short_text(raw_item.get("theme"), 120),
                "today_open_change": _short_text(raw_item.get("today_open_change"), 40),
                "label": _short_text(raw_item.get("label"), 80),
                "theme_level": _short_text(raw_item.get("theme_level"), 120),
                "reason": _short_text(raw_item.get("reason"), 800),
                follow_key: _short_text(raw_item.get(follow_key), 800),
            }
        )
    items.sort(key=lambda item: item["rank"])
    return items


def _safe_rank(value: object, *, fallback: int) -> int:
    try:
        rank = int(value)
    except Exception:
        return fallback
    return rank if rank > 0 else fallback


def _safe_text_list(value: object, *, limit: int, item_limit: int) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value is None or value == "":
        raw_items = []
    else:
        raw_items = [value]
    items: list[str] = []
    for item in raw_items[:limit]:
        text = _short_text(item, item_limit)
        if text:
            items.append(text)
    return items


def _safe_auction_list(value: object, *, limit: int) -> list[object]:
    if not isinstance(value, list):
        return []
    return [_safe_auction_json(item, limit=limit) for item in value[:limit]]


def _safe_auction_json(value: object, *, limit: int = 50) -> object:
    if isinstance(value, dict):
        return {str(key): _safe_auction_json(item, limit=limit) for key, item in list(value.items())[:limit]}
    if isinstance(value, list):
        return [_safe_auction_json(item, limit=limit) for item in value[:limit]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _short_text(value, 500)


def _auction_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 3)
    except Exception:
        return None


def _auction_timings(payload: dict) -> dict:
    source = payload.get("timings") if isinstance(payload.get("timings"), dict) else {}
    keys = [
        "prearm_elapsed_seconds",
        "quote_fetch_elapsed_seconds",
        "theme_summary_elapsed_seconds",
        "theme_judge_elapsed_seconds",
        "stock_pool_elapsed_seconds",
        "stock_judge_elapsed_seconds",
        "push_elapsed_seconds",
        "total_elapsed_seconds",
        "post_auction_elapsed_seconds",
    ]
    timings = {}
    for key in keys:
        number = _auction_number(source.get(key) if isinstance(source, dict) and key in source else payload.get(key))
        if number is not None:
            timings[key] = number
    return timings


def _recent_auction_strength_reports(path: Path, *, limit: int = 20, trade_date: str = "", include_v2: bool = True) -> list[dict]:
    if not path.exists():
        return []
    reports: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            report = json.loads(line)
        except Exception:
            continue
        if isinstance(report, dict):
            public_report = _auction_strength_public_report(report, include_v2=include_v2)
            if trade_date and public_report.get("trade_date") != trade_date:
                continue
            reports.append(public_report)
        if len(reports) >= limit:
            break
    return reports


def _auction_strength_report_count(path: Path, *, trade_date: str = "") -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0
    for line in lines:
        if not line.strip():
            continue
        try:
            report = json.loads(line)
        except Exception:
            continue
        if not isinstance(report, dict):
            continue
        if trade_date and str(report.get("trade_date") or "").strip() != trade_date:
            continue
        total += 1
    return total


def _auction_strength_public_report(report: dict, *, include_v2: bool = True) -> dict:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    conclusion = report.get("global_conclusion") if isinstance(report.get("global_conclusion"), dict) else {}
    public_report = {
        "id": str(report.get("id") or ""),
        "request_id": str(report.get("request_id") or ""),
        "received_at": str(report.get("received_at") or ""),
        "source_ip": str(report.get("source_ip") or ""),
        "trade_date": str(report.get("trade_date") or ""),
        "analysis_time": str(report.get("analysis_time") or ""),
        "summary": {
            "one_sentence": str(summary.get("one_sentence") or ""),
            "selection_logic": str(summary.get("selection_logic") or ""),
            "data_limit": str(summary.get("data_limit") or ""),
        },
        "top5_strong_stocks": _public_auction_stock_items(report.get("top5_strong_stocks"), follow_key="observe_after_930"),
        "top5_avoid_stocks": _public_auction_stock_items(report.get("top5_avoid_stocks"), follow_key="risk_after_930"),
        "global_conclusion": {
            "strongest_stock_at_925": str(conclusion.get("strongest_stock_at_925") or ""),
            "strongest_theme_cluster": str(conclusion.get("strongest_theme_cluster") or ""),
            "most_over_expected_stock": str(conclusion.get("most_over_expected_stock") or ""),
            "best_capacity_confirmation": str(conclusion.get("best_capacity_confirmation") or ""),
            "biggest_negative_feedback": str(conclusion.get("biggest_negative_feedback") or ""),
            "one_sentence_for_930": str(conclusion.get("one_sentence_for_930") or ""),
        },
    }
    if not include_v2:
        return public_report
    public_report["global_conclusion"]["limit_open_emotion_anchors"] = (
        conclusion.get("limit_open_emotion_anchors") if isinstance(conclusion.get("limit_open_emotion_anchors"), list) else []
    )
    public_report.update(
        {
            "theme_gate_result": report.get("theme_gate_result") if isinstance(report.get("theme_gate_result"), dict) else {},
            "emotion_anchors": report.get("emotion_anchors") if isinstance(report.get("emotion_anchors"), list) else [],
            "timings": report.get("timings") if isinstance(report.get("timings"), dict) else {},
            "quote_provider": str(report.get("quote_provider") or ""),
            "source_csv": str(report.get("source_csv") or ""),
            "data_limit": report.get("data_limit") if isinstance(report.get("data_limit"), list) else [],
            "warnings": report.get("warnings") if isinstance(report.get("warnings"), list) else [],
            "raw_payload": report.get("raw_payload") if "raw_payload" in report else {},
        }
    )
    return public_report


def _public_auction_stock_items(value: object, *, follow_key: str) -> list[dict]:
    if not isinstance(value, list):
        return []
    items = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        items.append(
            {
                "rank": _safe_rank(raw_item.get("rank"), fallback=len(items) + 1),
                "code": str(raw_item.get("code") or ""),
                "name": str(raw_item.get("name") or ""),
                "theme": str(raw_item.get("theme") or ""),
                "today_open_change": str(raw_item.get("today_open_change") or ""),
                "label": str(raw_item.get("label") or ""),
                "theme_level": str(raw_item.get("theme_level") or ""),
                "reason": str(raw_item.get("reason") or ""),
                follow_key: str(raw_item.get(follow_key) or ""),
            }
        )
    items.sort(key=lambda item: item["rank"])
    return items


def _assert_webhook_secret(*, expected: str, header_value: str, query: str) -> None:
    expected = expected.strip()
    if not expected:
        return
    query_secret = ""
    for part in query.split("&"):
        key, _, value = part.partition("=")
        if key in {"secret", "token"}:
            query_secret = unquote(value)
            break
    if header_value.strip() != expected and query_secret.strip() != expected:
        raise AuthError("webhook secret mismatch", status=401)


def _webhook_event_from_request(*, payload: object, headers: dict[str, str], source_ip: str, request_id: str) -> dict:
    received_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    normalized = _normalize_webhook_payload(payload, headers)
    return {
        "id": uuid4().hex,
        "request_id": request_id,
        "received_at": received_at,
        "source_ip": source_ip,
        "source": normalized["source"],
        "event_type": normalized["event_type"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "payload": payload,
        "headers": _safe_webhook_headers(headers),
    }


def _normalize_webhook_payload(payload: object, headers: dict[str, str]) -> dict[str, str]:
    data = payload if isinstance(payload, dict) else {}
    source = _first_text(
        data.get("source"),
        data.get("platform"),
        data.get("provider"),
        data.get("app"),
        headers.get("x-webhook-source"),
        headers.get("user-agent"),
        "unknown",
    )
    event_type = _first_text(
        data.get("event"),
        data.get("event_type"),
        data.get("type"),
        data.get("action"),
        headers.get("x-event-type"),
        "message",
    )
    title = _first_text(
        data.get("title"),
        data.get("name"),
        data.get("subject"),
        data.get("message"),
        data.get("text"),
        f"{source} / {event_type}",
    )
    summary = _first_text(
        data.get("summary"),
        data.get("description"),
        data.get("content"),
        data.get("message"),
        data.get("text"),
        _short_json(payload, 220),
    )
    return {
        "source": _short_text(source, 80),
        "event_type": _short_text(event_type, 80),
        "title": _short_text(title, 140),
        "summary": _short_text(summary, 260),
    }


def _append_webhook_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _recent_webhook_events(path: Path, *, limit: int = 30) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(_webhook_public_event(event))
        if len(events) >= limit:
            break
    return events


def _webhook_event_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


def _webhook_public_event(event: dict) -> dict:
    return {
        "id": str(event.get("id") or ""),
        "request_id": str(event.get("request_id") or ""),
        "received_at": str(event.get("received_at") or ""),
        "source_ip": str(event.get("source_ip") or ""),
        "source": str(event.get("source") or "unknown"),
        "event_type": str(event.get("event_type") or "message"),
        "title": str(event.get("title") or "Webhook event"),
        "summary": str(event.get("summary") or ""),
        "payload": event.get("payload") if "payload" in event else {},
        "headers": event.get("headers") if isinstance(event.get("headers"), dict) else {},
    }


def _safe_webhook_headers(headers: dict[str, str]) -> dict[str, str]:
    blocked = {"authorization", "cookie", "x-webhook-secret"}
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in blocked and not key.lower().startswith("x-forwarded")
    }


def _first_text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            text = _short_json(value, 160)
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _short_json(value: object, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        text = str(value)
    return _short_text(text, limit)


def _short_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _read_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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
