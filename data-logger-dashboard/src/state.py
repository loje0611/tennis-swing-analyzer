import streamlit as st
from collections import deque
from datetime import datetime
from queue import Queue
from src.config import MAX_QUEUE_SIZE, MODEL_PATH
from src.ble_manager import RealBLEManager

# Edge Impulse Import
try:
    from edge_impulse_linux.runner import ImpulseRunner
except ImportError:
    ImpulseRunner = None
    print("Edge Impulse Library not found")

# Constants
VIS_BUFFER_SIZE = 200
INFERENCE_WINDOW_SIZE = 50  # 1000ms at 50Hz
# MODEL_PATH is imported from src.config


@st.cache_resource
def get_cached_ble_manager():
    """Connection Persistence — Global Singleton."""
    print("Initializing RealBLEManager (Cached)")
    return RealBLEManager(Queue(maxsize=MAX_QUEUE_SIZE))


def init_session_state():
    """Initialize all session state variables."""
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
