import os
import atexit
import streamlit as st
from collections import deque
from datetime import datetime
from queue import Queue
from src.config import MAX_QUEUE_SIZE, INFERENCE_WINDOW_SAMPLES, INFERENCE_BUFFER_SIZE
from src.ble_manager import RealBLEManager
from src.settings_persistence import get_settings

# Edge Impulse Import
try:
    from edge_impulse_linux.runner import ImpulseRunner
except ImportError:
    ImpulseRunner = None
    print("Edge Impulse Library not found")

# Constants
VIS_BUFFER_SIZE = 200
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")


@st.cache_resource
def get_cached_ble_manager():
    """Connection Persistence — Global Singleton. Registers atexit for graceful BLE disconnect."""
    print("Initializing RealBLEManager (Cached)")
    manager = RealBLEManager(Queue(maxsize=MAX_QUEUE_SIZE))
    atexit.register(manager.stop)
    return manager


def load_model_safe(model_path):
    """Safely unloads existing model if present, then loads the new model."""
    if 'runner' in st.session_state and st.session_state.runner is not None:
        try:
            print("Stopping previous ImpulseRunner to free resources...")
            st.session_state.runner.stop()
        except Exception as e:
            print(f"Error stopping runner: {e}")
            
    st.session_state.runner = None
    st.session_state.model_info = None
    st.session_state.model_load_error = None
    st.session_state.current_model_path = model_path
    
    if not model_path or not os.path.exists(model_path):
        st.session_state.model_load_error = "Model file not found"
        return False
        
    if ImpulseRunner:
        try:
            runner = ImpulseRunner(model_path)
            model_info = runner.init()
            st.session_state.runner = runner
            st.session_state.model_info = model_info
            print(f"Model loaded successfully: {model_info['project']['owner']} / {model_info['project']['name']}")
            return True
        except Exception as e:
            print(f"Failed to load model from {model_path}: {e}")
            st.session_state.model_load_error = str(e)
            return False
    else:
        st.session_state.model_load_error = "Edge Impulse Library not found"
        return False


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
    if 'operation_mode' not in st.session_state: st.session_state.operation_mode = '🎾 코트 모드'
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

    # TTS (Text-to-Speech) State — persisted via settings.json
    if 'tts_enabled' not in st.session_state:
        st.session_state.tts_enabled = get_settings().get("tts_enabled", False)
    if 'tts_message' not in st.session_state: st.session_state.tts_message = ""
    if 'tts_swing_id' not in st.session_state: st.session_state.tts_swing_id = ""
    if 'tts_last_spoken_id' not in st.session_state: st.session_state.tts_last_spoken_id = ""
    
    # Data Logger TTS State
    if 'last_peak_time' not in st.session_state: st.session_state.last_peak_time = 0.0
    if 'pacing_guide_triggered' not in st.session_state: st.session_state.pacing_guide_triggered = False
    if 'session_peak_count' not in st.session_state: st.session_state.session_peak_count = 0

    # Data Logger UI: peak vline, mini chart, batch progress, total files saved
    if 'last_peak_samples_ago' not in st.session_state: st.session_state.last_peak_samples_ago = 9999
    if 'last_captured_swing_data' not in st.session_state: st.session_state.last_captured_swing_data = []
    if 'total_files_saved' not in st.session_state: st.session_state.total_files_saved = 0
    if 'batch_swings_target' not in st.session_state: st.session_state.batch_swings_target = 10

    # AI Model State
    if 'current_model_path' not in st.session_state:
        st.session_state.current_model_path = None
        
    if 'runner' not in st.session_state:
        st.session_state.runner = None
        st.session_state.model_info = None
        st.session_state.model_load_error = None
        
        # Try to auto-load the first available model if models dir exists
        if os.path.exists(MODELS_DIR):
            eim_files = [f for f in os.listdir(MODELS_DIR) if f.endswith('.eim')]
            if eim_files:
                default_model = os.path.join(MODELS_DIR, eim_files[0])
                load_model_safe(default_model)
            else:
                st.session_state.model_load_error = "No .eim models found in models directory"
        else:
             st.session_state.model_load_error = "Models directory not found"

    # The buffer size must be larger than INFERENCE_WINDOW_SAMPLES to allow for asymmetric slicing 
    # (e.g., 20 past samples + 40 future samples). 150 samples = 3 seconds of buffer.
    if 'inference_buffer' not in st.session_state or getattr(st.session_state.inference_buffer, "maxlen", 0) != INFERENCE_BUFFER_SIZE:
        st.session_state.inference_buffer = deque(maxlen=INFERENCE_BUFFER_SIZE)
    if 'inference_result' not in st.session_state:
        st.session_state.inference_result = {"label": "Idle", "score": 0.0}
    if 'inference_probabilities' not in st.session_state:
        st.session_state.inference_probabilities = {}
    if 'inference_debug_buffer_len' not in st.session_state:
        st.session_state.inference_debug_buffer_len = 0
    if 'inference_error' not in st.session_state:
        st.session_state.inference_error = None


