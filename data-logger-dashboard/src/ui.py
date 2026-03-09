import streamlit as st
import subprocess
import os
import time
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go

from src.config import MAX_QUEUE_SIZE, SERVICE_UUID, INFERENCE_WINDOW_SAMPLES

# 차트/게이지 한계치 (ESP32 ±2000dps, ±16g 확장 반영)
GYRO_AXIS_RANGE = [-2000, 2000]
ACCEL_AXIS_RANGE = [-16, 16]
GAUGE_MAX_KMH = 180
from src.data_manager import save_data_to_csv
from src.styles import styles
from src.state import init_session_state, load_model_safe, MODELS_DIR
from src.tts import render_tts_audio_button, render_tts_speaker
from src.inference import process_data_queue


# --- 공통 UI 헬퍼 함수 ---
def _render_tts_if_needed():
    """TTS Speaker 렌더링 (새 스윙 이벤트가 있을 때만)"""
    if st.session_state.get('tts_enabled', False):
        swing_id = st.session_state.get('tts_swing_id', '')
        last_spoken = st.session_state.get('tts_last_spoken_id', '')
        if swing_id and swing_id != last_spoken:
            render_tts_speaker(
                st.session_state.get('tts_message', ''),
                swing_id
            )
            st.session_state.tts_last_spoken_id = swing_id


def _render_ai_debug_log():
    """AI 실시간 확률 로그 (디버깅용)"""
    st.markdown("---")
    st.markdown("### 🔍 AI 실시간 확률 로그 (디버깅용)")
    
    debug_info = f"Buffer: {st.session_state.get('inference_debug_buffer_len', 0)}/{INFERENCE_WINDOW_SAMPLES}"
    debug_info += f" | AI Model: {'Loaded' if st.session_state.get('runner') else 'None'}"
    st.caption(debug_info)
    
    if st.session_state.get('inference_error'):
        st.error(f"Inference Error: {st.session_state.inference_error}")
        
    prob_dict = st.session_state.get('continuous_probabilities', {})
    if prob_dict:
        log_text = ""
        for label, score in prob_dict.items():
            log_text += f"- **{label}**: {score*100:.1f}%\n"
        st.markdown(log_text)
    else:
        st.caption("대기 중... (스윙 시 확률이 표시됩니다)")

# Try to import fragment (Streamlit 1.37+)
try:
    from streamlit import fragment
except ImportError:
    try:
        from streamlit import experimental_fragment as fragment
    except ImportError:
        fragment = None


def render_sidebar():
    with st.sidebar:
        st.title("⚙️ System Control")
        
        # 1. Connection Status
        st.markdown("### 📡 Connection")
        if st.session_state.get('ble_manager') and st.session_state.ble_manager.connected:
            st.success("🟢 Connected")
            
            # Sensor hardware error detection
            if st.session_state.ble_manager.sensor_status == "error":
                st.error("🔴 Sensor HW Error (MPU6050 not found)")
            
            if st.button("Disconnect", type="secondary"):
                if 'disconnect_func' in st.session_state:
                    st.session_state.disconnect_func()
        else:
            st.error("⚪ Disconnected")
            
        st.markdown("---")

        # 2. TTS Audio Control
        st.markdown("### 🔊 Audio")
        render_tts_audio_button()
        
        st.markdown("---")

        # 3. Dual mode: 코트 / 섀도우 (동적 모델 선택)
        st.markdown("### 🎾 동작 모드")
        mode_options = ["🎾 코트 모드", "🏠 섀도우 모드"]
        current_mode = st.session_state.get("operation_mode", "🎾 코트 모드")
        idx = 0 if current_mode == mode_options[0] else 1
        st.session_state.operation_mode = st.radio(
            "모드",
            mode_options,
            index=idx,
            key="operation_mode_radio",
            label_visibility="collapsed"
        )

        st.markdown("---")

        # 4. AI Model Status
        st.markdown("### 🤖 AI Model Settings")
        
        # Scan and list models
        eim_files = []
        if os.path.exists(MODELS_DIR):
            eim_files = [f for f in os.listdir(MODELS_DIR) if f.endswith('.eim')]
            
        if not eim_files:
            st.warning("No .eim models found in models folder.")
        else:
            current_idx = 0
            if getattr(st.session_state, 'current_model_path', None):
                current_base = os.path.basename(st.session_state.current_model_path)
                if current_base in eim_files:
                    current_idx = eim_files.index(current_base)
            
            selected_model = st.selectbox(
                "Select Model File",
                eim_files,
                index=current_idx,
                key="model_selectbox"
            )
            
            # If the user changed the model via selectbox, reload it
            if selected_model:
                selected_model_path = os.path.join(MODELS_DIR, selected_model)
                if getattr(st.session_state, 'current_model_path', None) != selected_model_path:
                    with st.spinner(f"Loading {selected_model}..."):
                        load_model_safe(selected_model_path)
                    st.rerun()
        
        if st.session_state.get('model_load_error'):
            st.warning(f"⚠️ Error: {st.session_state.model_load_error}")
        elif st.session_state.get('runner'):
            st.success("✅ Model Loaded Active")
        else:
            st.info("ℹ️ Not available")

        st.markdown("---")

        # 5. Page Navigation
        st.session_state.active_page = st.radio(
            "📋 Menu",
            ["🔥 Live Coaching", "💾 Data Logger"],
            index=0 if st.session_state.active_page == "🔥 Live Coaching" else 1,
            key="nav_radio"
        )
        
        st.markdown("---")
        
        # 6. System Settings
        with st.expander("🛠️ Settings & WiFi"):
            # Queue Status
            if 'data_queue' in st.session_state:
                q_size = st.session_state.data_queue.qsize()
                st.caption(f"Buffer: {q_size}/{MAX_QUEUE_SIZE}")

            # Smart WiFi 
            if st.button("WiFi Scan"):
                 st.info("Scanning...")
                 pass 

            # Reboot System
            if st.button("🔄 Reboot System"):
                st.session_state.show_reboot_confirm = True

            # Shutdown
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
    st.markdown("## 👋 Welcome to Tennis Analyst")
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

        # 5. Status / Watchdog: BLE timeout & ERR:NO_SENSOR are shown at top in main app

        # 6. TTS Speaker & AI Debug Log
        _render_tts_if_needed()
        _render_ai_debug_log()

    @fragment(run_every=0.5)
    def render_logger_tab():
        process_data_queue()

        # Header: Labeling Settings
        with st.expander("🏷️ Labeling Settings", expanded=True):
             c1, c2 = st.columns(2)
             with c1:
                  st.session_state.main_category = st.selectbox("Category", ["Forehand", "Backhand"], key="main_cat_log")
             with c2:
                  st.session_state.sub_category = st.selectbox("Type", ["Flat", "Topspin", "Slice"], key="sub_cat_log")

        # Debug Info (Hidden by default)
        with st.expander("🐞 Debug Metrics"):
             if 'last_max_mag' in st.session_state:
                  time_diff = datetime.now().timestamp() - st.session_state.get('last_peak_time', 0)
                  st.caption(f"Max Mag: {st.session_state.last_max_mag:.2f} G (Thresh: 3.0) | Time since peak: {time_diff:.1f}s")
             
        col_ctrl, col_sample, col_swing = st.columns([2, 1, 1])
        with col_ctrl:
            if not st.session_state.is_logging:
                if st.button("🔴 Start Logging", type="primary", use_container_width=True):
                    start_logging()
            else:
                if st.button("💾 Stop & Save", type="primary", use_container_width=True):
                    confirm_stop_logging()

        with col_sample:
            count = len(st.session_state.log_buffer)
            st.metric("Samples", count)
            
        with col_swing:
            swings = st.session_state.get('session_peak_count', 0)
            st.metric("Swings", swings)

        # Save Confirmation
        if st.session_state.get('show_save_confirm', False):
            st.warning("Save recorded data?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ YES (Save)"): save_and_stop()
            with c2:
                if st.button("🗑️ NO (Discard)"): discard_and_stop()

        # Detailed Graphs (Plotly: fixed axis for ±16g accel, ±2000dps gyro)
        if len(st.session_state.vis_buffer) > 0:
            df = pd.DataFrame(st.session_state.vis_buffer)
            st.caption("Accelerometer (X, Y, Z) — ±16g")
            acc_fig = go.Figure()
            for col in ['accel_x', 'accel_y', 'accel_z']:
                acc_fig.add_trace(go.Scatter(y=df[col], name=col, mode='lines'))
            acc_fig.update_layout(height=200, margin=dict(l=40, r=20, t=20, b=30), yaxis_range=ACCEL_AXIS_RANGE, template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(acc_fig, use_container_width=True, key="logger_accel")

            st.caption("Gyroscope (X, Y, Z) — ±2000 dps")
            gyro_fig = go.Figure()
            for col in ['gyro_x', 'gyro_y', 'gyro_z']:
                gyro_fig.add_trace(go.Scatter(y=df[col], name=col, mode='lines'))
            gyro_fig.update_layout(height=200, margin=dict(l=40, r=20, t=20, b=30), yaxis_range=GYRO_AXIS_RANGE, template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(gyro_fig, use_container_width=True, key="logger_gyro")

        # TTS Speaker & AI Debug Log
        _render_tts_if_needed()
        _render_ai_debug_log()

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
    st.session_state.tts_message = f"{main} {sub}, 로깅을 시작합니다."
    st.session_state.tts_swing_id = f"start_{time.time()}"
    # Prevent premature "Next" by setting it to True initially
    # It will be reset to False only after a valid peak is detected
    st.session_state.pacing_guide_triggered = True 
    st.session_state.last_peak_time = time.time()  # Reset cooldown
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
    st.session_state.tts_message = f"{count}회 스윙, 로깅을 종료합니다."
    st.session_state.tts_swing_id = f"end_{time.time()}"
    
    if st.session_state.log_buffer:
        try:
            fp = save_data_to_csv(st.session_state.log_buffer, st.session_state.main_category, st.session_state.sub_category)
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
    st.session_state.tts_message = f"{count}회 스윙, 로깅을 취소합니다."
    st.session_state.tts_swing_id = f"discard_{time.time()}"

    st.toast("Discarded", icon="🗑️")
    
    # Wait briefly for TTS to trigger before rerun
    time.sleep(0.5)
    st.rerun()
