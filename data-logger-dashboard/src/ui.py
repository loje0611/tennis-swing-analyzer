import streamlit as st
import subprocess
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go

from src.config import MAX_QUEUE_SIZE, SERVICE_UUID
from src.data_manager import save_data_to_csv
from src.styles import styles
from src.state import init_session_state
from src.tts import render_tts_audio_button, render_tts_speaker
from src.inference import process_data_queue

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

        # 3. AI Model Status
        st.markdown("### 🤖 AI Model")
        if st.session_state.get('model_load_error'):
            st.warning(f"⚠️ Error: {st.session_state.model_load_error}")
        elif st.session_state.get('runner'):
            st.success("✅ Loaded")
        else:
            st.info("ℹ️ Not available")

        st.markdown("---")

        # 3. Page Navigation
        st.session_state.active_page = st.radio(
            "📋 Menu",
            ["🔥 Live Coaching", "💾 Data Logger"],
            index=0 if st.session_state.active_page == "🔥 Live Coaching" else 1,
            key="nav_radio"
        )
        
        st.markdown("---")
        
        # 4. System Settings
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
        if swing_type == "Forehand":
            display_class = "swing-fh"
            label_color_class = "swing-label-fh"
        elif swing_type == "Backhand":
            display_class = "swing-bh"
            label_color_class = "swing-label-bh"
        
        display_text = swing_type.upper()
        
        # 1. Main Swing Card (with colored label text)
        st.markdown(f"""
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
                    'range': [0, 150],
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
                    {'range': [110, 130], 'color': '#4a2a0a'},
                    {'range': [130, 150], 'color': '#4a1a1a'}
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
                badge_class = "shot-badge-fh" if shot_type == "FH" else "shot-badge-bh"
                shots_html += f'<span class="shot-badge {badge_class}">{shot_type} {shot_speed:.0f}km</span>'
            shots_html += '</div>'
            st.markdown(shots_html, unsafe_allow_html=True)

        # 4. Swing Counters
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Forehand Count", st.session_state.swing_count_fh)
        with c2:
            st.metric("Backhand Count", st.session_state.swing_count_bh)

        # 5. Status Warning
        if st.session_state.get('ble_manager') and st.session_state.ble_manager.sensor_status == "error":
            st.error("🚨 센서 하드웨어 오류: MPU6050 센서가 감지되지 않습니다. 배선을 확인해 주세요.")
        else:
            time_since_last = (datetime.now() - st.session_state.get('last_data_time', datetime.now())).total_seconds()
            if time_since_last > 2.0:
                st.warning("⚠️ No data from sensor (Sleeping?)")

        # 6. TTS Speaker (client-side speech synthesis)
        if st.session_state.get('tts_enabled', False):
            swing_id = st.session_state.get('tts_swing_id', '')
            last_spoken = st.session_state.get('tts_last_spoken_id', '')
            if swing_id and swing_id != last_spoken:
                render_tts_speaker(
                    st.session_state.get('tts_message', ''),
                    swing_id
                )
                st.session_state.tts_last_spoken_id = swing_id

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
             
        col_ctrl, col_info = st.columns([2, 1])
        with col_ctrl:
            if not st.session_state.is_logging:
                if st.button("🔴 Start Logging", type="primary", use_container_width=True):
                    start_logging()
            else:
                if st.button("💾 Stop & Save", type="primary", use_container_width=True):
                    confirm_stop_logging()

        with col_info:
            count = len(st.session_state.log_buffer)
            st.metric("Samples", count)

        # Save Confirmation
        if st.session_state.get('show_save_confirm', False):
            st.warning("Save recorded data?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ YES (Save)"): save_and_stop()
            with c2:
                if st.button("🗑️ NO (Discard)"): discard_and_stop()

        # Detailed Graphs
        if len(st.session_state.vis_buffer) > 0:
            df = pd.DataFrame(st.session_state.vis_buffer)
            st.caption("Accelerometer (X, Y, Z)")
            st.line_chart(df[['accel_x', 'accel_y', 'accel_z']], height=200)
            
            st.caption("Gyroscope (X, Y, Z)")
            st.line_chart(df[['gyro_x', 'gyro_y', 'gyro_z']], height=200)

        # TTS Speaker (client-side speech synthesis)
        if st.session_state.get('tts_enabled', False):
            swing_id = st.session_state.get('tts_swing_id', '')
            last_spoken = st.session_state.get('tts_last_spoken_id', '')
            if swing_id and swing_id != last_spoken:
                render_tts_speaker(
                    st.session_state.get('tts_message', ''),
                    swing_id
                )
                st.session_state.tts_last_spoken_id = swing_id

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
    import time
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
    import time
    count = st.session_state.get('session_peak_count', 0)
    st.session_state.tts_message = f"{count}회 스윙, 로깅을 종료합니다."
    st.session_state.tts_swing_id = f"end_{time.time()}"
    
    if st.session_state.log_buffer:
        try:
            fp = save_data_to_csv(st.session_state.log_buffer, st.session_state.main_category, st.session_state.sub_category)
            st.toast(f"Saved: {fp}", icon="✅")
        except Exception as e:
            st.error(f"Error: {e}")
        except Exception as e:
            st.error(f"Error: {e}")
    
    # Wait briefly for TTS to trigger before rerun
    time.sleep(0.5)
    st.rerun()

def discard_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    st.session_state.log_buffer = []
    st.session_state.log_buffer = []

    # TTS Announcement: Discard Logging
    import time
    count = st.session_state.get('session_peak_count', 0)
    st.session_state.tts_message = f"{count}회 스윙, 로깅을 취소합니다."
    st.session_state.tts_swing_id = f"discard_{time.time()}"

    st.toast("Discarded", icon="🗑️")
    
    # Wait briefly for TTS to trigger before rerun
    time.sleep(0.5)
    st.rerun()
