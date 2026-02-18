import streamlit as st
import time
import subprocess
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime
from queue import Queue
from src.config import MAX_QUEUE_SIZE, SERVICE_UUID
from src.data_manager import save_data_to_csv
from src.ble_manager import RealBLEManager
import math
import plotly.graph_objects as go

# Edge Impulse Import
try:
    from edge_impulse_linux.runner import ImpulseRunner
except ImportError:
    ImpulseRunner = None
    print("Edge Impulse Library not found")

# Try to import fragment (Streamlit 1.37+)
try:
    from streamlit import fragment
except ImportError:
    try:
        from streamlit import experimental_fragment as fragment
    except ImportError:
        fragment = None

# Visualization buffer size
VIS_BUFFER_SIZE = 200
INFERENCE_WINDOW_SIZE = 50  # 1000ms at 50Hz
MODEL_PATH = "/home/keunu/tennis-swing-analyzer/model.eim"

# --- 1. Connection Persistence (Global Singleton) ---
@st.cache_resource
def get_cached_ble_manager():
    print("Initializing RealBLEManager (Cached)")
    return RealBLEManager(Queue(maxsize=MAX_QUEUE_SIZE))

def init_session_state():
    # --- Auto-Recovery ---
    if 'ble_manager' not in st.session_state:
        st.session_state.ble_manager = get_cached_ble_manager()
        st.session_state.data_queue = st.session_state.ble_manager.data_queue

    if st.session_state.ble_manager.connected:
        if 'view' not in st.session_state or st.session_state.view != 'collection':
            st.session_state.view = 'collection'
            st.toast("🔄 Connection Auto-Recovered", icon="🔗")
            st.session_state.is_logging = False

    # Basic State
    if 'view' not in st.session_state: st.session_state.view = 'connection'
    if 'vis_buffer' not in st.session_state: st.session_state.vis_buffer = deque(maxlen=VIS_BUFFER_SIZE)
    if 'log_buffer' not in st.session_state: st.session_state.log_buffer = []
    if 'is_logging' not in st.session_state: st.session_state.is_logging = False
    if 'collection_state' not in st.session_state: st.session_state.collection_state = 'ready'
    if 'main_category' not in st.session_state: st.session_state.main_category = 'Forehand'
    if 'sub_category' not in st.session_state: st.session_state.sub_category = 'Flat'
    if 'active_page' not in st.session_state: st.session_state.active_page = '🔥 Live Coaching'
    if 'last_data_time' not in st.session_state: st.session_state.last_data_time = datetime.now()
    if 'show_save_confirm' not in st.session_state: st.session_state.show_save_confirm = False
    
    # Swing Counting & Analysis State
    if 'swing_count_fh' not in st.session_state: st.session_state.swing_count_fh = 0
    if 'swing_count_bh' not in st.session_state: st.session_state.swing_count_bh = 0
    if 'last_predicted_label' not in st.session_state: st.session_state.last_predicted_label = "Idle"
    if 'current_power' not in st.session_state: st.session_state.current_power = 0.0

    # Speed Measurement State
    if 'peak_speed_2s' not in st.session_state: st.session_state.peak_speed_2s = 0.0
    if 'speed_history' not in st.session_state: st.session_state.speed_history = deque()
    if 'last_swing_speed' not in st.session_state: st.session_state.last_swing_speed = 0.0
    if 'current_speed_kmh' not in st.session_state: st.session_state.current_speed_kmh = 0.0

    # Last Swing Retention
    if 'last_swing_type' not in st.session_state: st.session_state.last_swing_type = "Ready"

    # Gauge Flickering Prevention
    if 'last_gauge_value' not in st.session_state: st.session_state.last_gauge_value = 0.0
    if 'force_gauge_update' not in st.session_state: st.session_state.force_gauge_update = False

    # Recent Shots History (last 5)
    if 'recent_shots' not in st.session_state: st.session_state.recent_shots = deque(maxlen=5)

    # AI Model State
    if 'runner' not in st.session_state:
        st.session_state.runner = None
        st.session_state.model_info = None
        st.session_state.model_load_error = None
        
        if ImpulseRunner:
            try:
                runner = ImpulseRunner(MODEL_PATH)
                model_info = runner.init()
                st.session_state.runner = runner
                st.session_state.model_info = model_info
                print(f"Model loaded: {model_info['project']['owner']} / {model_info['project']['name']}")
            except Exception as e:
                print(f"Failed to load model: {e}")
                st.session_state.model_load_error = str(e)

    if 'inference_buffer' not in st.session_state:
        st.session_state.inference_buffer = deque(maxlen=INFERENCE_WINDOW_SIZE)
    if 'inference_result' not in st.session_state:
        st.session_state.inference_result = {"label": "Idle", "score": 0.0}

def styles():
    st.markdown("""
        <style>
        /* Global Font Adjustments */
        html, body, [class*="css"] {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }
        
        /* Metric Styling */
        div[data-testid="stMetricValue"] {
            font-size: 3rem !important;
            font-weight: 700;
        }
        
        /* Big Swing Card */
        .swing-card {
            border-radius: 20px;
            padding: 40px 20px;
            text-align: center;
            margin-bottom: 20px;
            color: white;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }
        .swing-fh { 
            background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%); 
            border: 4px solid #1e7e34; 
        }
        .swing-bh { 
            background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); 
            border: 4px solid #0056b3; 
        }
        .swing-ready { 
            background: linear-gradient(135deg, #343a40 0%, #23272b 100%); 
            border: 4px solid #23272b; 
        }
        
        .swing-title { font-size: 2rem; opacity: 0.9; margin: 0; font-weight: 500; letter-spacing: 1px; }
        .swing-label { font-size: 6rem; font-weight: 900; margin: 10px 0; line-height: 1.0; text-transform: uppercase; }
        .swing-speed { font-size: 2.5rem; font-weight: 700; background: rgba(0,0,0,0.2); padding: 5px 20px; border-radius: 10px; display: inline-block; margin-top: 15px; }

        /* Status Text Colors */
        .swing-label-ready { color: #888888; }
        .swing-label-fh { color: #00CC66; }
        .swing-label-bh { color: #3366FF; }

        /* Recent Shots Badges */
        .shot-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 1rem;
            margin: 4px;
            color: white;
        }
        .shot-badge-fh { background: linear-gradient(135deg, #28a745, #1e7e34); }
        .shot-badge-bh { background: linear-gradient(135deg, #007bff, #0056b3); }

        /* Tabs Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 60px;
            white-space: pre-wrap;
            background-color: #1e1e1e;
            border-radius: 10px;
            color: white;
            font-size: 1.2rem;
            width: 100%;
            justify-content: center;
        }
        .stTabs [aria-selected="true"] {
            background-color: #ff4b4b !important;
            color: white !important;
        }
        
        /* Sidebar — theme-aware */
        @media (prefers-color-scheme: light) {
            section[data-testid="stSidebar"] {
                background-color: #f5f5f5;
                color: #222;
            }
            section[data-testid="stSidebar"] h1,
            section[data-testid="stSidebar"] h2,
            section[data-testid="stSidebar"] h3,
            section[data-testid="stSidebar"] p,
            section[data-testid="stSidebar"] span,
            section[data-testid="stSidebar"] label {
                color: #222 !important;
            }
        }
        @media (prefers-color-scheme: dark) {
            section[data-testid="stSidebar"] {
                background-color: #111;
                color: #eee;
            }
        }
        
        </style>
    """, unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ System Control")
        
        # 1. Connection Status
        st.markdown("### 📡 Connection")
        if st.session_state.get('ble_manager') and st.session_state.ble_manager.connected:
            st.success("🟢 Connected")
            
            if st.button("Disconnect", type="secondary"):
                if 'disconnect_func' in st.session_state:
                    st.session_state.disconnect_func()
        else:
            st.error("⚪ Disconnected")
            
        st.markdown("---")

        # 2. Page Navigation
        st.session_state.active_page = st.radio(
            "📋 Menu",
            ["🔥 Live Coaching", "💾 Data Logger"],
            index=0 if st.session_state.active_page == "🔥 Live Coaching" else 1,
            key="nav_radio"
        )
        
        st.markdown("---")
        
        # 3. System Settings
        with st.expander("🛠️ Settings & WiFi"):
            # Queue Status
            if 'data_queue' in st.session_state:
                q_size = st.session_state.data_queue.qsize()
                st.caption(f"Buffer: {q_size}/{MAX_QUEUE_SIZE}")

            # Smart WiFi 
            if st.button("WiFi Scan"):
                 st.info("Scanning...")
                 pass 

            # Hard Reset
            if st.button("⚠️ Hard Reset"):
                 st.cache_resource.clear()
                 if st.session_state.get('ble_manager'):
                     st.session_state.ble_manager.stop()
                 st.rerun()

            # Shutdown
            if st.button("🛑 Shutdown System"):
                st.session_state.show_shutdown_confirm = True

        if st.session_state.get('show_shutdown_confirm', False):
            st.error("Are you sure?")
            if st.button("Yes, Shutdown"):
                subprocess.run(["sudo", "shutdown", "-h", "now"])

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

def process_data_queue():
    """Fetch data from queue, calculate speed, and count swings."""
    if 'data_queue' in st.session_state:
        q = st.session_state.data_queue
        
        # Skip if lagging (only when not logging)
        if not st.session_state.is_logging and q.qsize() > 1000:
            while not q.empty():
                try: q.get_nowait()
                except: break
            return

        items = []
        while not q.empty():
            try: items.append(q.get_nowait())
            except: break
        
        if items:
            st.session_state.last_data_time = datetime.now()
            
            # --- Speed Calculation (Physics) ---
            # V = r * omega (r = 0.5m)
            last_item = items[-1]
            gx, gy, gz = last_item['gyro_x'], last_item['gyro_y'], last_item['gyro_z']
            gyro_mag = np.sqrt(gx**2 + gy**2 + gz**2) # deg/s
            rad_s = math.radians(gyro_mag)
            v_mps = 0.5 * rad_s
            v_kmh = v_mps * 3.6
            st.session_state.current_speed_kmh = v_kmh

            # --- Peak Speed History (2s Window) for Gauge Display ---
            now = datetime.now()
            st.session_state.speed_history.append((now, v_kmh))
            
            # Remove old data (> 2.0s)
            while st.session_state.speed_history and (now - st.session_state.speed_history[0][0]).total_seconds() > 2.0:
                st.session_state.speed_history.popleft()
            
            # Update Peak Speed (for Gauge)
            if st.session_state.speed_history:
                st.session_state.peak_speed_2s = max(s[1] for s in st.session_state.speed_history)
            else:
                st.session_state.peak_speed_2s = 0.0

            # --- Buffer Updates ---
            st.session_state.vis_buffer.extend(items)
            if st.session_state.is_logging:
                st.session_state.log_buffer.extend(items)
            
            # --- Inference & Counting ---
            if st.session_state.get('runner'):
                for item in items:
                    st.session_state.inference_buffer.append([
                        item['accel_x'], item['accel_y'], item['accel_z'],
                        item['gyro_x'], item['gyro_y'], item['gyro_z']
                    ])
                
                if len(st.session_state.inference_buffer) == INFERENCE_WINDOW_SIZE:
                    features = []
                    for sample in st.session_state.inference_buffer:
                        features.extend(sample)
                    
                    try:
                        res = st.session_state.runner.classify(features)
                        if 'result' in res and 'classification' in res['result']:
                            classifications = res['result']['classification']
                            best_label = max(classifications, key=classifications.get)
                            best_score = classifications[best_label]
                            
                            # Update raw inference result
                            st.session_state.inference_result = {
                                "label": best_label,
                                "score": best_score
                            }

                            # --- Swing Counting & Max Speed Capture Logic ---
                            # Logic: Transition FROM Idle TO Forehand/Backhand
                            current_label = best_label if best_score > 0.75 else "Idle"
                            prev_label = st.session_state.last_predicted_label
                            
                            if current_label != prev_label:
                                if current_label == "Forehand" and prev_label != "Forehand":
                                    st.session_state.swing_count_fh += 1
                                    st.session_state.last_swing_speed = st.session_state.peak_speed_2s
                                    st.session_state.last_swing_type = "Forehand"
                                    st.session_state.force_gauge_update = True
                                    st.session_state.recent_shots.append(("FH", st.session_state.peak_speed_2s))
                                    
                                elif current_label == "Backhand" and prev_label != "Backhand":
                                    st.session_state.swing_count_bh += 1
                                    st.session_state.last_swing_speed = st.session_state.peak_speed_2s
                                    st.session_state.last_swing_type = "Backhand"
                                    st.session_state.force_gauge_update = True
                                    st.session_state.recent_shots.append(("BH", st.session_state.peak_speed_2s))
                                
                                # Do NOT update last_swing_type if shifting back to Idle
                                # This ensures the UI "Retains" the last valid swing
                                
                                st.session_state.last_predicted_label = current_label

                    except Exception as e:
                        print(f"Inference error: {e}")

            if st.session_state.get('ble_manager'):
                st.session_state.ble_manager.queue_overflow_count = 0

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
        time_since_last = (datetime.now() - st.session_state.get('last_data_time', datetime.now())).total_seconds()
        if time_since_last > 2.0:
            st.warning("⚠️ No data from sensor (Sleeping?)")

    @fragment(run_every=0.5)
    def render_logger_tab():
        process_data_queue()

        # Header: Labeling Settings (Moved here)
        with st.expander("🏷️ Labeling Settings", expanded=True):
             c1, c2 = st.columns(2)
             with c1:
                  st.session_state.main_category = st.selectbox("Category", ["Forehand", "Backhand"], key="main_cat_log")
             with c2:
                  st.session_state.sub_category = st.selectbox("Type", ["Flat", "Topspin", "Slice"], key="sub_cat_log")

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

def confirm_stop_logging():
    st.session_state.show_save_confirm = True

def save_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    if st.session_state.log_buffer:
        try:
            fp = save_data_to_csv(st.session_state.log_buffer, st.session_state.main_category, st.session_state.sub_category)
            st.toast(f"Saved: {fp}", icon="✅")
        except Exception as e:
            st.error(f"Error: {e}")
    st.rerun()

def discard_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    st.session_state.log_buffer = []
    st.toast("Discarded", icon="🗑️")
    st.rerun()
