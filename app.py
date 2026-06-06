from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from trade_review_agent.alerts import (
    AlertPlan,
    evaluate_plans,
    event_dedupe_key,
    load_plans,
    save_plans,
)
from trade_review_agent.alert_tts import generate_voice_line, synthesize_edge_tts
from trade_review_agent.config import load_env, openai_configured
from trade_review_agent.ocr_trades import screenshot_to_trade_csv, trade_file_to_trade_csv
from trade_review_agent.visual_report import build_all_reports


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "work" / "uploads"
REPORT_DIR = BASE_DIR / "outputs" / "streamlit_reports"
CACHE_DB = BASE_DIR / "work" / "real_trade_review_cache.sqlite"
ALERT_PLANS = BASE_DIR / "work" / "alert_plans.json"
TTS_DIR = BASE_DIR / "work" / "tts"


def main() -> None:
    load_env(BASE_DIR / ".env")
    st.set_page_config(page_title="A股交易复盘 Agent", layout="wide")
    st.title("A股交易复盘 Agent")
    st.caption("交割单复盘 + 预案盯盘提醒。先把交易变成结构化数据，再用行情和规则辅助执行。")
    if os.getenv("SHOW_OPENAI_STATUS", "").strip().lower() in {"1", "true", "yes"}:
        if openai_configured():
            st.sidebar.success("OpenAI API Key configured")
        else:
            st.sidebar.warning("OpenAI API Key not configured")

    review_tab, alert_tab = st.tabs(["复盘报告", "交易提醒"])
    with review_tab:
        _render_review_tab()
    with alert_tab:
        _render_alert_tab()


def _render_review_tab() -> None:
    uploaded = st.file_uploader("上传交割单 / 成交记录", type=["xls", "xlsx", "csv", "txt"])
    screenshots = st.file_uploader(
        "上传成交记录截图（OpenAI 视觉识别）",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )

    if screenshots:
        st.caption("截图会交给 OpenAI 视觉模型读取；Excel/CSV/TXT 也会先交给 AI 理解交易事实。")
        preview_cols = st.columns(min(3, len(screenshots)))
        for idx, image in enumerate(screenshots[:3]):
            preview_cols[idx % len(preview_cols)].image(image, caption=image.name, width="stretch")

    if not uploaded and not screenshots:
        st.info("请上传券商导出的成交记录文件，或者直接上传交割单截图。")
    elif uploaded:
        st.success(f"已选择结构化文件：{uploaded.name}")
    else:
        st.info("当前没有结构化文件，将从截图自动识别成交记录。建议上传包含完整股票名、买卖方向、时间、价格和数量的清晰截图。")

    if (uploaded or screenshots) and st.button("生成复盘报告", type="primary"):
        run_id = uuid4().hex
        run_dir = REPORT_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        with st.spinner("正在读取成交记录、拉取行情并生成 visual report..."):
            saved_screenshots = _save_screenshots(screenshots, run_dir)
            trades_path = _prepare_trades_path(uploaded, saved_screenshots, run_dir)

            ocr_preview = _read_ocr_preview(trades_path) if not uploaded else None
            results = build_all_reports(
                trades_path=trades_path,
                output_dir=run_dir,
                cache_db=CACHE_DB,
            )

        st.session_state["last_run_dir"] = str(run_dir)
        st.session_state["last_trades_path"] = str(trades_path)
        st.session_state["last_ocr_preview"] = ocr_preview
        st.session_state["last_screenshots"] = [str(path) for path in saved_screenshots]
        st.session_state["last_results"] = [
            {
                "title": result.title,
                "rating": result.rating,
                "score": result.score,
                "trade_type": result.trade_type,
                "path": str(result.output),
            }
            for result in results
        ]
        st.success(f"已生成 {len(results)} 份 visual report。")

    if "last_results" in st.session_state:
        _render_results(st.session_state["last_results"], Path(st.session_state["last_run_dir"]))


def _render_alert_tab() -> None:
    st.subheader("交易预案提醒")
    st.caption("页面打开时定时拉取实时行情；触发预案后页面提醒，并尝试语音播报。浏览器可能要求先点击页面后才允许播放声音。")

    plans = load_plans(ALERT_PLANS)
    _alert_plan_form(plans)
    plans = load_plans(ALERT_PLANS)

    if not plans:
        st.info("还没有预案。先添加一个股票和触发价，例如：跌破止损价提醒卖出，突破观察价提醒加仓/确认。")
        return

    st.divider()
    monitor = st.toggle("开启实时盯盘提醒", value=False, key="monitor_alerts")
    refresh_seconds = st.slider("刷新间隔（秒）", min_value=10, max_value=120, value=30, step=5)
    persona = st.selectbox("提醒人格", ["可爱AI女友", "专业交易员"], index=0)
    st.session_state["alert_persona"] = persona

    st.subheader("预案列表")
    _render_plan_table(plans)
    _render_simulation_test(plans)

    if monitor:
        quotes, events, errors = evaluate_plans(plans)
        if errors:
            st.warning("部分行情接口失败：" + "；".join(errors[:3]))
        _render_quote_table(quotes)
        _render_alert_events(events)
        _auto_refresh(refresh_seconds)
    else:
        st.info("盯盘提醒已暂停。")


def _alert_plan_form(plans: list[AlertPlan]) -> None:
    with st.expander("新增交易预案", expanded=not plans):
        with st.form("alert_plan_form", clear_on_submit=True):
            cols = st.columns([1, 1, 1, 1])
            code = cols[0].text_input("证券代码", placeholder="600584")
            name = cols[1].text_input("名称", placeholder="长电科技")
            action = cols[2].text_input("建议动作", placeholder="减仓 / 止损 / 加仓确认")
            enabled = cols[3].checkbox("启用", value=True)
            thesis = st.text_area("预案理由", placeholder="例如：跌破前低说明短线强度失效；突破前高且板块强势则确认。")
            cols = st.columns(4)
            stop_loss = cols[0].number_input("止损价 <=", min_value=0.0, value=0.0, step=0.01)
            take_profit = cols[1].number_input("止盈价 >=", min_value=0.0, value=0.0, step=0.01)
            breakout = cols[2].number_input("突破价 >=", min_value=0.0, value=0.0, step=0.01)
            breakdown = cols[3].number_input("跌破价 <=", min_value=0.0, value=0.0, step=0.01)
            submitted = st.form_submit_button("保存预案", type="primary")
        if submitted:
            if not code.strip():
                st.error("请填写证券代码。")
                return
            plans.append(
                AlertPlan(
                    plan_id=uuid4().hex,
                    code=code.strip().zfill(6)[-6:],
                    name=name.strip() or code.strip(),
                    action=action.strip() or "执行预案",
                    thesis=thesis.strip(),
                    stop_loss=_none_if_zero(stop_loss),
                    take_profit=_none_if_zero(take_profit),
                    breakout=_none_if_zero(breakout),
                    breakdown=_none_if_zero(breakdown),
                    enabled=enabled,
                )
            )
            save_plans(ALERT_PLANS, plans)
            st.success("预案已保存。")
            st.rerun()

    if plans and st.button("清空全部预案"):
        save_plans(ALERT_PLANS, [])
        st.rerun()


def _render_plan_table(plans: list[AlertPlan]) -> None:
    frame = pd.DataFrame(
        [
            {
                "启用": plan.enabled,
                "代码": plan.code,
                "名称": plan.name,
                "动作": plan.action,
                "止损<=": plan.stop_loss,
                "止盈>=": plan.take_profit,
                "突破>=": plan.breakout,
                "跌破<=": plan.breakdown,
                "理由": plan.thesis,
            }
            for plan in plans
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)


def _render_quote_table(quotes) -> None:
    if not quotes:
        return
    st.subheader("实时行情")
    frame = pd.DataFrame(
        [
            {
                "代码": quote.code,
                "名称": quote.name,
                "现价": quote.price,
                "涨跌幅": f"{quote.pct_chg:.2f}%",
                "时间": quote.quote_time,
            }
            for quote in quotes
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)


def _render_alert_events(events) -> None:
    st.subheader("触发提醒")
    if not events:
        st.success("当前没有触发预案。")
        return

    seen = st.session_state.setdefault("alert_seen_keys", set())
    for event in events:
        key = event_dedupe_key(event)
        st.error(event.message)
        st.caption(f"预案理由：{event.plan.thesis or '未填写'}")
        if key not in seen:
            seen.add(key)
            _play_alert(event.message, st.session_state.get("alert_persona", "可爱AI女友"))


def _render_simulation_test(plans: list[AlertPlan]) -> None:
    st.subheader("模拟触发测试")
    with st.expander("点击后立即触发，测试页面提醒和声音播报", expanded=False):
        labels = [f"{plan.code} {plan.name} - {plan.action}" for plan in plans]
        selected = st.selectbox("选择要测试的预案", labels)
        plan = plans[labels.index(selected)]
        default_price = plan.take_profit or plan.breakout or plan.stop_loss or plan.breakdown or 0.0
        cols = st.columns([1, 1])
        simulated_price = cols[0].number_input("假设现价", min_value=0.0, value=float(default_price), step=0.01)
        fire = cols[1].button("开始模拟触发", type="primary")
        if fire:
            message = (
                f"模拟测试：假设现在 {plan.name} {plan.code} 拉到 {simulated_price:.2f}，"
                f"触发预案：{plan.action}。"
            )
            st.error(message)
            _play_alert(message, st.session_state.get("alert_persona", "可爱AI女友"))


def _play_alert(message: str, persona: str = "可爱AI女友") -> None:
    safe_message = message.replace("\\", "\\\\").replace("`", "\\`")
    voice_message, drafts = generate_voice_line(message, persona)
    safe_voice_message = voice_message.replace("\\", "\\\\").replace("`", "\\`")
    pitch = 1.35 if persona == "可爱AI女友" else 1.0
    rate = 1.08 if persona == "可爱AI女友" else 1.0
    frequency = 1046 if persona == "可爱AI女友" else 880
    audio_uri = ""
    try:
        audio_path = synthesize_edge_tts(voice_message, TTS_DIR)
        audio_uri = audio_path.as_uri()
    except Exception as exc:
        st.warning(f"Edge TTS 生成失败，已退回浏览器语音：{exc}")
    with st.expander("本次提醒文案代理", expanded=False):
        st.write(f"最终播报：{voice_message}")
        for draft in drafts:
            st.caption(f"{draft.agent}：{draft.text}")
    components.html(
        f"""
        <script>
        const message = `{safe_message}`;
        const voiceMessage = `{safe_voice_message}`;
        const audioUri = `{audio_uri}`;
        try {{
          const context = new (window.AudioContext || window.webkitAudioContext)();
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          oscillator.type = "sine";
          oscillator.frequency.value = {frequency};
          oscillator.connect(gain);
          gain.connect(context.destination);
          gain.gain.setValueAtTime(0.001, context.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.2, context.currentTime + 0.02);
          oscillator.start();
          gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.8);
          oscillator.stop(context.currentTime + 0.85);
        }} catch (err) {{}}
        if (audioUri) {{
          try {{
            const audio = new Audio(audioUri);
            audio.autoplay = true;
            audio.play().catch(() => {{
              const utter = new SpeechSynthesisUtterance(voiceMessage);
              utter.lang = "zh-CN";
              utter.rate = {rate};
              utter.pitch = {pitch};
              window.speechSynthesis.cancel();
              window.speechSynthesis.speak(utter);
            }});
          }} catch (err) {{}}
        }} else {{
          try {{
          const utter = new SpeechSynthesisUtterance(voiceMessage);
          utter.lang = "zh-CN";
          utter.rate = {rate};
          utter.pitch = {pitch};
          const voices = window.speechSynthesis.getVoices();
          const preferred = voices.find(v => /Chinese|Mandarin|Ting|Huihui|Yaoyao|Xiaoxiao|zh/i.test(v.name + v.lang));
          if (preferred) utter.voice = preferred;
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utter);
          }} catch (err) {{}}
        }}
        </script>
        """,
        height=0,
    )


def _auto_refresh(seconds: int) -> None:
    components.html(
        f"""
        <script>
        setTimeout(() => {{
          window.parent.location.reload();
        }}, {seconds * 1000});
        </script>
        """,
        height=0,
    )


def _none_if_zero(value: float) -> float | None:
    return None if value <= 0 else float(value)


def _prepare_trades_path(uploaded, saved_screenshots: list[Path], run_dir: Path) -> Path:
    if uploaded:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        suffix = Path(uploaded.name).suffix or ".xls"
        upload_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
        upload_path.write_bytes(uploaded.getbuffer())
        ai_csv = run_dir / "ai_trades.csv"
        return trade_file_to_trade_csv(upload_path, ai_csv)

    if not saved_screenshots:
        raise ValueError("没有可识别的成交记录来源")

    ai_csv = run_dir / "ai_trades.csv"
    return screenshot_to_trade_csv(saved_screenshots, ai_csv)


def _read_ocr_preview(path: Path) -> list[dict] | None:
    if not path.exists() or path.suffix.lower() != ".csv":
        return None
    try:
        frame = pd.read_csv(path)
    except Exception:
        return None
    return frame.head(50).to_dict(orient="records")


def _render_results(results: list[dict], run_dir: Path) -> None:
    st.subheader("成交数据")
    trades_path = Path(st.session_state.get("last_trades_path", ""))
    if trades_path.exists():
        st.markdown(f"[打开本次结构化成交数据]({trades_path.as_uri()})")

    ocr_preview = st.session_state.get("last_ocr_preview")
    if ocr_preview:
        st.caption("OCR 识别结果预览。若某一列识别错了，可以先导出成交记录文件再上传，或者继续优化 OCR 模板。")
        st.dataframe(ocr_preview, width="stretch", hide_index=True)

    st.subheader("复盘报告目录")
    st.dataframe(
        [
            {
                "报告": item["title"],
                "交易类型": item["trade_type"],
                "评级": item["rating"],
                "评分": item["score"],
            }
            for item in results
        ],
        width="stretch",
        hide_index=True,
    )

    index_path = run_dir / "index.html"
    if index_path.exists():
        st.markdown(f"[打开总目录]({index_path.as_uri()})")

    screenshots = [Path(path) for path in st.session_state.get("last_screenshots", [])]
    if screenshots:
        st.subheader("截图凭证")
        cols = st.columns(min(3, len(screenshots)))
        for idx, path in enumerate(screenshots):
            if path.exists():
                cols[idx % len(cols)].image(str(path), caption=path.name, width="stretch")

    selected = st.selectbox("选择一份报告预览", [item["title"] for item in results])
    selected_item = next(item for item in results if item["title"] == selected)
    selected_path = Path(selected_item["path"])
    if selected_path.exists():
        components.html(selected_path.read_text(encoding="utf-8"), height=900, scrolling=True)

    st.subheader("全部报告链接")
    for item in results:
        path = Path(item["path"])
        cols = st.columns([4, 1, 1, 2])
        cols[0].markdown(f"**{item['title']}**")
        cols[1].markdown(f"评级：`{item['rating']}`")
        cols[2].markdown(f"评分：`{item['score']}`")
        cols[3].markdown(f"[打开报告]({path.as_uri()})")


def _save_screenshots(files, run_dir: Path) -> list[Path]:
    if not files:
        return []
    screenshot_dir = run_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for file in files:
        suffix = Path(file.name).suffix.lower() or ".png"
        path = screenshot_dir / f"{Path(file.name).stem}_{uuid4().hex[:8]}{suffix}"
        path.write_bytes(file.getbuffer())
        saved.append(path)
    return saved


if __name__ == "__main__":
    main()
