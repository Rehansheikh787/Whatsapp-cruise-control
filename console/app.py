"""
console/app.py

Streamlit real-time monitoring dashboard and operations console for WhatsApp Cruise Control.
Auto-refreshes every 2 seconds, displaying live message triage, relationship badges,
layered decisions, generated replies, and Chroma semantic retrieval grounding traces.

Features full operational controls:
  - Atomic config/settings.json updates (DRY_RUN vs LIVE, min/max delays).
  - Prominent emergency Kill Switch button with banner.
  - Live activity metrics and grounding traces.
"""

import json
import os
from pathlib import Path
import tempfile
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Set page config
st.set_page_config(
    page_title="WhatsApp Cruise Control",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 1. Auto-refresh every 2 seconds (2000 ms)
st_autorefresh(interval=2000, key="console_feed_refresh")

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_FILE = REPO_ROOT / "logs" / "console_feed.jsonl"
SETTINGS_FILE = REPO_ROOT / "config" / "settings.json"
KILL_SWITCH_FILE = REPO_ROOT / "kill_switch.flag"

# Default fallback settings
DEFAULT_SETTINGS: dict = {
    "dry_run": True,
    "min_delay_seconds": 3,
    "max_delay_seconds": 12,
}

# Relationship badge color mapping
RELATIONSHIP_COLORS = {
    "family": {"bg": "#ecfdf5", "text": "#065f46", "border": "#10b981"},       # green
    "friend": {"bg": "#eff6ff", "text": "#1e40af", "border": "#3b82f6"},       # blue
    "professional": {"bg": "#f5f3ff", "text": "#5b21b6", "border": "#8b5cf6"}, # purple
    "unknown": {"bg": "#f3f4f6", "text": "#374151", "border": "#9ca3af"},      # gray
    "group": {"bg": "#f3f4f6", "text": "#374151", "border": "#9ca3af"},        # gray
}

# Decision badge styling
DECISION_COLORS = {
    "reply": {"bg": "#dcfce7", "text": "#15803d", "label": "REPLY"},
    "ignore": {"bg": "#fee2e2", "text": "#991b1b", "label": "IGNORE"},
}

# Custom styling for dashboard
st.markdown(
    """
    <style>
    .metric-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
    }
    .feed-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge {
        display: inline-block;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 600;
        border-radius: 9999px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .reply-box {
        background-color: #f0fdf4;
        border-left: 4px solid #22c55e;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin-top: 10px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .reason-text {
        color: #4b5563;
        font-size: 13px;
        font-style: italic;
    }
    .kill-banner {
        background-color: #fef2f2;
        border: 2px solid #ef4444;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 20px;
        color: #991b1b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_settings() -> dict:
    """Reads config/settings.json safely with resilient fallback defaults."""
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                return merged
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def atomic_save_settings(new_settings: dict) -> None:
    """
    Atomically writes settings dictionary to config/settings.json using a temp file
    and atomic rename so concurrent readers never see an incomplete write.
    """
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        "w",
        dir=SETTINGS_FILE.parent,
        delete=False,
        encoding="utf-8"
    )
    temp_path = Path(temp_file.name)
    try:
        json.dump(new_settings, temp_file, indent=2, ensure_ascii=False)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_path, SETTINGS_FILE)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise e


def load_logs() -> tuple[list[dict], int, int]:
    """
    Reads all log entries from logs/console_feed.jsonl.
    Returns:
        tuple (all_entries, total_processed, total_replies)
    """
    if not LOGS_FILE.exists():
        return [], 0, 0

    entries: list[dict] = []
    total_processed = 0
    total_replies = 0

    try:
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    entries.append(data)
                    total_processed += 1
                    if data.get("decision") == "reply" or data.get("reply"):
                        total_replies += 1
                except json.JSONDecodeError:
                    continue
    except Exception:
        return [], 0, 0

    return entries, total_processed, total_replies


# Load current runtime state
all_entries, total_processed, total_replies = load_logs()
recent_entries = list(reversed(all_entries[-20:]))  # last 20 lines, newest first
current_settings = load_settings()
kill_switch_active = KILL_SWITCH_FILE.exists()

# --- TOP KILL SWITCH BANNER ---
if kill_switch_active:
    st.markdown(
        """
        <div class="kill-banner">
            <h3 style="margin: 0 0 6px 0; color: #dc2626;">🚨 KILL SWITCH ACTIVE</h3>
            <span>All automated message processing and sending are completely halted. The WhatsApp client is ignoring all incoming activity.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_k1, _ = st.columns([1, 4])
    with col_k1:
        if st.button("🟢 Clear Kill Switch", key="clear_kill_switch_banner", use_container_width=True):
            try:
                KILL_SWITCH_FILE.unlink(missing_ok=True)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to clear kill switch: {e}")

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚡ Cruise Control")
    st.caption("Autonomous WhatsApp Co-Pilot")
    st.divider()

    # 1. EMERGENCY KILL SWITCH
    st.subheader("Safety Guard")
    if not kill_switch_active:
        if st.button("🛑 KILL SWITCH", type="primary", use_container_width=True, help="Immediately halt all WhatsApp bot processing"):
            KILL_SWITCH_FILE.touch()
            st.rerun()
    else:
        st.error("🛑 Kill switch is ENGAGED")
        if st.button("Clear Kill Switch", key="clear_kill_switch_sidebar", use_container_width=True):
            KILL_SWITCH_FILE.unlink(missing_ok=True)
            st.rerun()
    st.divider()

    # 2. OPERATING MODE (DRY_RUN vs LIVE)
    st.subheader("Operating Mode")
    mode_options = ["DRY_RUN (Simulation)", "LIVE (Active Replies)"]
    current_dry_run = current_settings.get("dry_run", True)
    current_idx = 0 if current_dry_run else 1

    selected_mode = st.radio(
        "Select Mode:",
        options=mode_options,
        index=current_idx,
        help="In DRY_RUN, replies are generated and logged but never sent over WhatsApp. LIVE sends actual WhatsApp replies to allowlisted contacts.",
    )
    new_dry_run = (selected_mode == mode_options[0])

    if new_dry_run != current_dry_run:
        updated = load_settings()
        updated["dry_run"] = new_dry_run
        atomic_save_settings(updated)
        st.rerun()

    if new_dry_run:
        st.warning("🟡 **Simulation Mode**: Replies logged, none sent.")
    else:
        st.success("🟢 **Live Mode**: Sending replies to allowlisted contacts.")

    st.divider()

    # 3. HUMANIZED DELAY CONTROLS
    st.subheader("Humanized Delay Range")
    st.caption("Random jitter delay (in seconds) applied before sending each reply.")

    curr_min = int(current_settings.get("min_delay_seconds", 3))
    curr_max = int(current_settings.get("max_delay_seconds", 12))

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        new_min = st.number_input(
            "Min (s)",
            min_value=1,
            max_value=60,
            value=curr_min,
            step=1,
        )
    with col_d2:
        new_max = st.number_input(
            "Max (s)",
            min_value=1,
            max_value=120,
            value=curr_max,
            step=1,
        )

    # Validation: both positive, min strictly less than max
    if new_min >= new_max:
        st.error("Min delay must be strictly less than Max delay.")
    else:
        if new_min != curr_min or new_max != curr_max:
            updated = load_settings()
            updated["min_delay_seconds"] = int(new_min)
            updated["max_delay_seconds"] = int(new_max)
            atomic_save_settings(updated)
            st.rerun()

    st.divider()

    # 4. ACTIVITY METRICS
    st.subheader("Activity Metrics")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("Total Triage", total_processed)
    with col_m2:
        st.metric("Replies Sent", total_replies)

    ignored_count = max(0, total_processed - total_replies)
    st.metric("Ignored / Filtered", ignored_count)
    st.divider()

    st.caption("⏱️ *Auto-refreshing every 2s*")


# --- MAIN CONSOLE FEED ---
st.title("Live Triage Console")
st.caption("Real-time stream of incoming WhatsApp messages, safety gates, and authentic persona responses.")

if not recent_entries:
    # Graceful empty state
    st.info("📡 Waiting for first message... (Start `whatsapp/baileys_client.js` or run `agent/bridge.py` to stream activity)")
else:
    for idx, item in enumerate(recent_entries):
        timestamp = item.get("timestamp", "Unknown time")
        jid = item.get("jid", "unknown@jid")
        rel = (item.get("relationship") or "unknown").lower()
        decision = (item.get("decision") or "ignore").lower()
        reason = item.get("reason", "no reason provided")
        reply = item.get("reply")
        retrieval_trace = item.get("retrieval_trace") or []

        # Color configurations
        rel_style = RELATIONSHIP_COLORS.get(rel, RELATIONSHIP_COLORS["unknown"])
        dec_style = DECISION_COLORS.get(decision, DECISION_COLORS["ignore"])

        with st.container():
            # Header row: Badges + Timestamp
            badge_html = f"""
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div>
                    <span class="badge" style="background-color: {rel_style['bg']}; color: {rel_style['text']}; border: 1px solid {rel_style['border']};">
                        {rel}
                    </span>
                    &nbsp;
                    <span class="badge" style="background-color: {dec_style['bg']}; color: {dec_style['text']};">
                        {dec_style['label']}
                    </span>
                    &nbsp;
                    <span style="font-weight: 500; font-size: 13px; color: #374151;">{jid}</span>
                </div>
                <div style="font-size: 12px; color: #9ca3af;">
                    {timestamp}
                </div>
            </div>
            """
            st.markdown(badge_html, unsafe_allow_html=True)

            # Reason
            st.markdown(f"<span class='reason-text'>Reason: {reason}</span>", unsafe_allow_html=True)

            # Reply section (if present)
            if reply:
                st.markdown(
                    f"""
                    <div class="reply-box">
                        <strong style="color: #15803d; font-size: 12px;">GENERATED REPLY:</strong><br/>
                        <span style="color: #1f2937; font-size: 14px;">{reply}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Expandable retrieval trace
            if retrieval_trace:
                with st.expander(f"🔍 Retrieval Trace ({len(retrieval_trace)} grounding examples)"):
                    for t_idx, trace in enumerate(retrieval_trace, 1):
                        their_msg = trace.get("their_message", "")
                        my_rep = trace.get("my_reply", "")
                        dist = trace.get("distance")
                        dist_str = f"{dist:.3f}" if dist is not None else "N/A"
                        conv = trace.get("conversation_id", "")

                        st.markdown(
                            f"""
                            **Example {t_idx}** *(Distance: `{dist_str}`, Source: `{conv}`)*:
                            - **Their past message:** *"{their_msg}"*
                            - **My past reply:** *"{my_rep}"*
                            """
                        )
            else:
                with st.expander("🔍 Retrieval Trace (None)"):
                    st.caption("No semantic past message grounding required or retrieved.")

            st.divider()
