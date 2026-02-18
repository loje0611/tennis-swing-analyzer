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
    if 'last_data_time' not in st.session_state: st.session_state.last_data_time = datetime.now()
    if 'show_save_confirm' not in st.session_state: st.session_state.show_save_confirm = False
    
    # Swing Counting & Analysis State
    if 'swing_count_fh' not in st.session_state: st.session_state.swing_count_fh = 0
    if 'swing_count_bh' not in st.session_state: st.session_state.swing_count_bh = 0
    if 'last_predicted_label' not in st.session_state: st.session_state.last_predicted_label = "Idle"
    if 'current_power' not in st.session_state: st.session_state.current_power = 0.0

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
        
        /* Big Result Card */
        .result-card {
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            margin-bottom: 20px;
            color: white;
            transition: all 0.3s ease;
        }
        .result-fh { background-color: #28a745; border: 4px solid #1e7e34; }
        .result-bh { background-color: #007bff; border: 4px solid #0056b3; }
        .result-idle { background-color: #343a40; border: 4px solid #23272b; }
        
        .result-title { font-size: 1.5rem; opacity: 0.8; margin: 0; }
        .result-label { font-size: 5rem; font-weight: 900; margin: 10px 0; line-height: 1.1; }
        .result-score { font-size: 1.2rem; opacity: 0.9; }
        
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
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #111;
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
            
            # Virtual Battery (Random for now)
            try:
                # battery usually between 3.3V and 4.2V, map to %?
                # Just mock it: 84%
                bat_level = 84 
                st.markdown(f"**🔋 Battery:** {bat_level}%")
                st.progress(bat_level / 100)
            except:
                pass
                
            if st.button("Disconnect", type="secondary"):
                if 'disconnect_func' in st.session_state:
                    st.session_state.disconnect_func()
        else:
            st.error("⚪ Disconnected")
            
        st.markdown("---")
        
        # 2. System Settings
        with st.expander("🛠️ Settings & WiFi"):
            # Queue Status
            if 'data_queue' in st.session_state:
                q_size = st.session_state.data_queue.qsize()
                st.caption(f"Buffer: {q_size}/{MAX_QUEUE_SIZE}")

            # Smart WiFi 
            if st.button("WiFi Scan"):
                 st.info("Scanning...")
                 # (WiFi Scan Logic skipped for brevity, keeping existing structure if needed, or simplified)
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
    """Fetch data from queue, calculate power, and count swings."""
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
            
            # --- Power Calculation (using last item) ---
            last_item = items[-1]
            ax, ay, az = last_item['accel_x'], last_item['accel_y'], last_item['accel_z']
            # Simple vector sum magnitude - gravity(1.0) approx
            # power = sqrt(x^2 + y^2 + z^2)
            power_g = np.sqrt(ax**2 + ay**2 + az**2)
            
            # Smoothing could be applied here preferably
            st.session_state.current_power = power_g

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
                            
                            # Update result
                            st.session_state.inference_result = {
                                "label": best_label,
                                "score": best_score
                            }

                            # --- Swing Counting Logic ---
                            # Logic: If we transition FROM Idle TO Forehand/Backhand with High Confidence
                            # AND we haven't counted it recently (simple debounce logic needed in real app, but here simple transition)
                            current_label = best_label if best_score > 0.75 else "Idle"
                            prev_label = st.session_state.last_predicted_label
                            
                            if current_label != prev_label:
                                if current_label == "Forehand" and prev_label != "Forehand":
                                    st.session_state.swing_count_fh += 1
                                elif current_label == "Backhand" and prev_label != "Backhand":
                                    st.session_state.swing_count_bh += 1
                                
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
        
        # 1. Result Card
        result = st.session_state.inference_result
        label = result['label']
        score = result['score']
        
        display_class = "result-idle"
        display_text = "Ready"
        
        if score > 0.7:
            display_text = label.upper()
            if label == "Forehand": display_class = "result-fh"
            elif label == "Backhand": display_class = "result-bh"
        else:
            display_text = "..."

        st.markdown(f"""
            <div class="result-card {display_class}">
                <p class="result-title">AI Analysis</p>
                <h1 class="result-label">{display_text}</h1>
                <p class="result-score">Confidence: {score*100:.0f}%</p>
            </div>
        """, unsafe_allow_html=True)

        # 2. Swing Counters
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
                <div style="background:#1e3a29; border-left: 5px solid #28a745; padding:15px; border-radius:5px;">
                    <span style="color:#aaa;">Forehand</span>
                    <div style="font-size:2.5rem; font-weight:bold; color:white;">{st.session_state.swing_count_fh}</div>
                </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
                <div style="background:#192e47; border-left: 5px solid #007bff; padding:15px; border-radius:5px;">
                    <span style="color:#aaa;">Backhand</span>
                    <div style="font-size:2.5rem; font-weight:bold; color:white;">{st.session_state.swing_count_bh}</div>
                </div>
            """, unsafe_allow_html=True)

        # 3. Power Meter
        st.markdown("### Swing Power (G)")
        power = st.session_state.current_power
        # Normalize roughly: 1G is rest, 5G is very strong
        progress_val = min(max((power - 1.0) / 4.0, 0.0), 1.0) 
        st.progress(progress_val)
        st.caption(f"Current Impact: {power:.2f} G")
        
        # 4. Status Warning
        time_since_last = (datetime.now() - st.session_state.get('last_data_time', datetime.now())).total_seconds()
        if time_since_last > 2.0:
            st.warning("⚠️ No data from sensor (Sleeping?)")

    @fragment(run_every=0.5)
    def render_logger_tab():
        # Update data occasionally
        # process_data_queue() # Already called in live metrics if visible? 
        # Actually tabs might hide elements. We should ensure process_data_queue is called.
        # But @fragment run_every might conflict if multiple are running. 
        # Let's assume user stays on one tab. 
        # Safest is to call process_data_queue here too, relying on the queue handling (it drains queue).
        process_data_queue()

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
    
    # Header area for labeling (Always visible)
    with st.expander("🏷️ Labeling Settings", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
             st.session_state.main_category = st.selectbox("Category", ["Forehand", "Backhand"], key="main_cat_top")
        with c2:
             st.session_state.sub_category = st.selectbox("Type", ["Flat", "Topspin", "Slice"], key="sub_cat_top")

    # Main Tabs
    tab_live, tab_log = st.tabs(["🎾 Live Coaching", "💾 Data Logger"])

    with tab_live:
        render_live_metrics()
    
    with tab_log:
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
