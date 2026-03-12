import streamlit as st
import subprocess
import os
import time
import pandas as pd
import plotly.graph_objects as go

from src.config import SERVICE_UUID

# 차트/게이지 한계치 (ESP32 ±16g 확장 반영)
GAUGE_MAX_KMH = 180
from src.data_manager import save_data_to_csv, get_label_file_counts
from src.styles import styles
from src.state import init_session_state, load_model_safe, MODELS_DIR
from src.tts import render_tts_audio_toggle, render_tts_request_write
from src.inference import process_data_queue


# --- 글로벌 헤더 (메인 화면 최상단, 모바일 가시성) ---
def render_global_header():
    """메인 영역 최상단: 앱 타이틀 + 센서 연결 상태 뱃지 (사이드바 접힐 때 대비)."""
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("## 🎾 Tennis Swing Analyzer")
    with col2:
        if st.session_state.get("ble_manager") and st.session_state.ble_manager.connected:
            if st.session_state.ble_manager.sensor_status == "error":
                st.error("🔴 Sensor Error")
            else:
                st.success("🟢 Sensor Connected")
        else:
            st.error("🔴 Disconnected")


# --- 공통 UI 헬퍼 함수 ---
def _render_tts_if_needed():
    """Fragment: write current TTS request to localStorage. The persistent listener
    (rendered in main script) polls and speaks; avoids 0.2s iframe replacement killing 'Next'."""
    render_tts_request_write(
        tts_enabled=st.session_state.get('tts_enabled', False),
        tts_message=st.session_state.get('tts_message', ''),
        tts_swing_id=st.session_state.get('tts_swing_id', ''),
    )


# Try to import fragment (Streamlit 1.37+)
try:
    from streamlit import fragment
except ImportError:
    try:
        from streamlit import experimental_fragment as fragment
    except ImportError:
        fragment = None


def _derive_operation_mode_from_filename(filename):
    """eim 파일명에서 코트/섀도우 모드 추론 (스플릿 브레인 방지)."""
    if not filename:
        return "🎾 코트 모드"
    name_lower = filename.lower()
    if "shadow" in name_lower:
        return "🏠 섀도우 모드"
    return "🎾 코트 모드"


def render_sidebar():
    with st.sidebar:
        st.title("⚙️ System Control")

        # 1. Menu (Live Coaching / Data Logger)
        st.markdown("### 📋 Menu")
        st.session_state.active_page = st.radio(
            "Menu",
            ["🔥 Live Coaching", "📊 Data Logger"],
            index=0 if st.session_state.active_page == "🔥 Live Coaching" else 1,
            key="nav_radio",
            label_visibility="collapsed"
        )
        st.markdown("---")

        # 2. AI Brain (eim 모델 선택 → operation_mode 자동 할당)
        st.markdown("### 🤖 AI Brain")
        eim_files = []
        if os.path.exists(MODELS_DIR):
            eim_files = [f for f in os.listdir(MODELS_DIR) if f.endswith('.eim')]

        if not eim_files:
            st.warning("No .eim models found.")
        else:
            current_idx = 0
            if getattr(st.session_state, 'current_model_path', None):
                current_base = os.path.basename(st.session_state.current_model_path)
                if current_base in eim_files:
                    current_idx = eim_files.index(current_base)

            selected_model = st.selectbox(
                "Model File",
                eim_files,
                index=current_idx,
                key="model_selectbox",
                label_visibility="collapsed"
            )

            if selected_model:
                selected_model_path = os.path.join(MODELS_DIR, selected_model)
                st.session_state.operation_mode = _derive_operation_mode_from_filename(selected_model)
                if getattr(st.session_state, 'current_model_path', None) != selected_model_path:
                    with st.spinner(f"Loading {selected_model}..."):
                        load_model_safe(selected_model_path)
                    st.rerun()

        if st.session_state.get('model_load_error'):
            st.warning(f"⚠️ {st.session_state.model_load_error}")
        elif st.session_state.get('runner'):
            st.success("✅ Model Loaded")
        else:
            st.caption("ℹ️ No model")
        st.markdown("---")

        # 3. Preferences (오디오 토글, settings.json 영구 저장)
        st.markdown("### 🔊 Preferences")
        render_tts_audio_toggle()
        st.markdown("---")

        # 4. Settings & WiFi (하단) — 사이드바는 이 한 곳에서만 렌더링 (중복 방지)
        with st.expander("🛠️ Settings & WiFi"):
            if st.button("WiFi Scan"):
                st.info("Scanning...")
            if st.button("🔄 Reboot System"):
                st.session_state.show_reboot_confirm = True
            if st.button("🛑 Shutdown System"):
                st.session_state.show_shutdown_confirm = True

            if st.session_state.get('show_reboot_confirm', False):
                st.warning("🔄 Reboot system?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, Reboot"):
                        subprocess.run(["sudo", "reboot"])
                with c2:
                    if st.button("Cancel Reboot"):
                        st.session_state.show_reboot_confirm = False
                        st.rerun()

            if st.session_state.get('show_shutdown_confirm', False):
                st.error("Are you sure?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, Shutdown"):
                        subprocess.run(["sudo", "shutdown", "-h", "now"])
                with c2:
                    if st.button("Cancel Shutdown"):
                        st.session_state.show_shutdown_confirm = False
                        st.rerun()

def render_connection_view(scan_callback):
    st.markdown("## 👋 Welcome to Tennis Swing Analyzer")
    st.info("Connect your sensor to start.")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("📡 SCAN & CONNECT", type="primary", use_container_width=True):
            with st.spinner("Searching for device..."):
                scan_callback()
        st.caption(f"Looking for Service UUID: {SERVICE_UUID}")


# --- Fragmented UI Components ---
if fragment:
    @fragment(run_every=0.1)
    def render_live_metrics():
        process_data_queue()
        
        # Display Logic: Use "Last Swing Retention"
        swing_type = st.session_state.last_swing_type  # "Ready", "Forehand", "Backhand"
        swing_speed = st.session_state.last_swing_speed
        
        display_class = "swing-ready"
        label_color_class = "swing-label-ready"
        if "Forehand" in swing_type:
            display_class = "swing-fh"
            label_color_class = "swing-label-fh"
        elif "Backhand" in swing_type:
            display_class = "swing-bh"
            label_color_class = "swing-label-bh"
        
        display_text = swing_type.upper()
        
        # Model display info
        model_name_display = os.path.basename(st.session_state.get('current_model_path', 'None')) if getattr(st.session_state, 'runner', None) else "No Model"
        
        # 1. Main Swing Card (with colored label text)
        st.markdown(f"""
            <div style="text-align:center; margin-bottom: 10px;">
               <span style="background-color: #333; padding: 4px 12px; border-radius: 12px; font-size: 0.9em; color: #aaa;">🧠 {model_name_display}</span>
            </div>
            <div class="swing-card {display_class}">
                <p class="swing-title">LAST DETECTED SWING</p>
                <h1 class="swing-label {label_color_class}">{display_text}</h1>
                <div class="swing-speed">{swing_speed:.1f} km/h</div>
            </div>
        """, unsafe_allow_html=True)

        # 2. Speed Gauge (Stable render — no st.empty() to avoid flicker)
        display_speed = st.session_state.peak_speed_2s
        
        should_update = (
            abs(display_speed - st.session_state.last_gauge_value) >= 1.0
            or st.session_state.force_gauge_update
        )
        
        if should_update:
            st.session_state.last_gauge_value = display_speed
            st.session_state.force_gauge_update = False
        
        render_speed = st.session_state.last_gauge_value
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = render_speed,
            number = {'font': {'size': 48, 'color': 'white'}, 'suffix': ' km/h'},
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "⚡ SWING SPEED", 'font': {'size': 16, 'color': '#aaa'}},
            gauge = {
                'axis': {
                    'range': [0, GAUGE_MAX_KMH],
                    'tickwidth': 2,
                    'tickcolor': '#666',
                    'dtick': 30,
                    'tickfont': {'size': 12, 'color': '#888'}
                },
                'bar': {'color': "#ff4b4b", 'thickness': 0.35},
                'bgcolor': '#1a1a1a',
                'borderwidth': 2,
                'bordercolor': '#333',
                'steps': [
                    {'range': [0, 50], 'color': '#1a3a1a'},
                    {'range': [50, 80], 'color': '#2a4a1a'},
                    {'range': [80, 110], 'color': '#4a4a0a'},
                    {'range': [110, 140], 'color': '#4a2a0a'},
                    {'range': [140, GAUGE_MAX_KMH], 'color': '#4a1a1a'}
                ],
                'threshold': {
                    'line': {'color': "#ff0040", 'width': 5},
                    'thickness': 0.8,
                    'value': render_speed
                }
            }
        ))
        fig.update_layout(
            height=220,
            margin=dict(l=25, r=25, t=40, b=15),
            paper_bgcolor="rgba(0,0,0,0)",
            font={'color': "white"}
        )
        st.plotly_chart(fig, use_container_width=True, key="speed_gauge")

        # 3. Recent Shots History (Badges)
        if st.session_state.recent_shots:
            shots_html = '<div style="text-align:center; margin: 10px 0 20px 0;">'
            shots_html += '<p style="color:#888; font-size:0.9rem; margin-bottom:8px;">📜 RECENT SHOTS</p>'
            for shot_type, shot_speed in st.session_state.recent_shots:
                badge_class = "shot-badge-fh" if shot_type.startswith("F") else "shot-badge-bh"
                shots_html += f'<span class="shot-badge {badge_class}">{shot_type} {shot_speed:.0f}km</span>'
            shots_html += '</div>'
            st.markdown(shots_html, unsafe_allow_html=True)

        # 4. Swing Counters
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Forehand Count", st.session_state.swing_count_fh)
        with c2:
            st.metric("Backhand Count", st.session_state.swing_count_bh)

        # 5. TTS: must run inside fragment so timer-driven runs inject "Next" / FH-BH announcements
        _render_tts_if_needed()

    @fragment(run_every=0.2)
    def render_logger_tab():
        # 큐 비우기 → vis_buffer 반영 (process_data_queue가 큐를 소비하고 vis_buffer에 추가)
        process_data_queue()

        # 메인 차트: st.empty() 없이 네이티브 st.line_chart만 사용 → DOM 유지, 플리커링 제거
        GYRO_NORM_DIVISOR = 125.0
        st.caption("📈 실시간 센서 (가속도 · 자이로 norm)")
        with st.container(height=450, border=False):
            buf = st.session_state.vis_buffer
            if len(buf) > 0:
                raw = pd.DataFrame(list(buf))
                df = pd.DataFrame({
                    "ax": raw["accel_x"],
                    "ay": raw["accel_y"],
                    "az": raw["accel_z"],
                    "gx_norm": raw["gyro_x"] / GYRO_NORM_DIVISOR,
                    "gy_norm": raw["gyro_y"] / GYRO_NORM_DIVISOR,
                    "gz_norm": raw["gyro_z"] / GYRO_NORM_DIVISOR,
                })
                st.line_chart(df, height=400)
            else:
                df_empty = pd.DataFrame(columns=["ax", "ay", "az", "gx_norm", "gy_norm", "gz_norm"])
                st.line_chart(df_empty, height=400)

        # 시인성 극대화: 현재 배치 수집 진행도 (큼지막한 숫자)
        target = st.session_state.get("batch_swings_target", 10)
        current = st.session_state.get("session_peak_count", 0)
        progress_val = min(1.0, current / target) if target > 0 else 0.0
        st.markdown("<p style='margin: 1rem 0 0.25rem 0; font-size: 0.95rem; color: #aaa;'>현재 파일 수집 진행도</p>", unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-size: 3.2rem; font-weight: bold; text-align: center; margin: 0.25rem 0; line-height: 1.2;'>{current} / {target} 스윙</p>",
            unsafe_allow_html=True,
        )
        st.progress(progress_val)

        # Start/Stop 버튼 — Expander 바깥에 상시 노출
        if not st.session_state.is_logging:
            if st.button("🔴 Start Logging", type="primary", use_container_width=True, key="btn_start_log"):
                start_logging()
        else:
            if st.button("💾 Stop & Save", type="primary", use_container_width=True, key="btn_stop_log"):
                confirm_stop_logging()

        if st.session_state.get("show_save_confirm", False):
            st.warning("저장할까요?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ 저장", key="btn_yes_save"):
                    save_and_stop()
            with c2:
                if st.button("🗑️ 취소", key="btn_no_discard"):
                    discard_and_stop()

        # 라벨 설정 (접기/펴기 가능)
        with st.expander("🏷️ 라벨 설정", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.session_state.main_category = st.selectbox("Category", ["Forehand", "Backhand"], key="main_cat_log")
            with c2:
                st.session_state.sub_category = st.selectbox("Type", ["Topspin", "Slice"], key="sub_cat_log")

        # 화면 하단: 라벨별 저장 파일 개수 (폴더 스캔, 저장 시마다 갱신)
        label_counts = get_label_file_counts()
        st.markdown("---")
        st.markdown("**📁 라벨별 수집 통계**")
        cols = st.columns(6)
        for idx, label in enumerate(sorted(label_counts.keys())):
            with cols[idx % 6]:
                st.metric(label=label, value=f"{label_counts[label]} 개")

        # TTS: must run inside fragment so "Next" and start message get injected on fragment runs
        _render_tts_if_needed()

else:
    # Fallback for old streamlit
    def render_live_metrics(): st.error("Update Streamlit for Live features")
    def render_logger_tab(): st.error("Update Streamlit")

def render_collection_view():
    init_session_state()
    styles()

    # Render active page based on sidebar selection
    if st.session_state.active_page == "🔥 Live Coaching":
        render_live_metrics()
    else:
        render_logger_tab()

# --- Helper Functions ---
def start_logging():
    st.session_state.is_logging = True
    st.session_state.log_buffer = []
    st.session_state.show_save_confirm = False
    
    # TTS Announcement: Start Logging
    st.session_state.logging_packet_count = 0
    main = st.session_state.main_category
    sub = st.session_state.sub_category
    st.session_state.tts_message = f"{main} {sub}, starting logging."
    st.session_state.tts_swing_id = f"start_{time.time()}"
    st.session_state.tts_sequence = st.session_state.get('tts_sequence', 0) + 1
    st.session_state.last_peak_time = time.time()
    st.session_state.session_peak_count = 0
    
    # Visual Confirmation
    st.toast(f"🔊 {st.session_state.tts_message}", icon="▶️")

def confirm_stop_logging():
    st.session_state.show_save_confirm = True

def save_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    
    # TTS Announcement: End Logging
    count = st.session_state.get('session_peak_count', 0)
    st.session_state.tts_message = f"{count} swings, stopping logging."
    st.session_state.tts_swing_id = f"end_{time.time()}"
    st.session_state.tts_sequence = st.session_state.get('tts_sequence', 0) + 1
    
    if st.session_state.log_buffer:
        try:
            fp = save_data_to_csv(st.session_state.log_buffer, st.session_state.main_category, st.session_state.sub_category)
            st.session_state.total_files_saved = st.session_state.get('total_files_saved', 0) + 1
            st.toast(f"Saved: {fp}", icon="✅")
        except Exception as e:
            st.error(f"Error: {e}")
    
    # Wait briefly for TTS to trigger before rerun
    time.sleep(0.5)
    st.rerun()

def discard_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    st.session_state.log_buffer = []

    # TTS Announcement: Discard Logging
    count = st.session_state.get('session_peak_count', 0)
    st.session_state.tts_message = f"{count} swings, logging cancelled."
    st.session_state.tts_swing_id = f"discard_{time.time()}"
    st.session_state.tts_sequence = st.session_state.get('tts_sequence', 0) + 1

    st.toast("Discarded", icon="🗑️")
    
    # Wait briefly for TTS to trigger before rerun
    time.sleep(0.5)
    st.rerun()
