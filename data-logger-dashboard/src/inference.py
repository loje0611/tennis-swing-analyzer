import streamlit as st
import numpy as np
import math
from datetime import datetime
from src.state import INFERENCE_WINDOW_SIZE


def process_data_queue():
    """Fetch data from queue, calculate speed, and count swings."""
    if 'data_queue' not in st.session_state:
        return

    q = st.session_state.data_queue
    
    # Skip if lagging (only when not logging)
    if not st.session_state.is_logging and q.qsize() > 1000:
        while not q.empty():
            try: q.get_nowait()
            except Exception: break
        return

    items = []
    while not q.empty():
        try: items.append(q.get_nowait())
        except Exception: break
    
    if not items:
        return

    st.session_state.last_data_time = datetime.now()
    
    # --- Speed Calculation (Physics) ---
    # V = r * omega (r = 0.5m)
    last_item = items[-1]
    gx, gy, gz = last_item['gyro_x'], last_item['gyro_y'], last_item['gyro_z']
    gyro_mag = np.sqrt(gx**2 + gy**2 + gz**2)  # deg/s
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
                        st.session_state.last_predicted_label = current_label

            except Exception as e:
                print(f"Inference error: {e}")

    if st.session_state.get('ble_manager'):
        st.session_state.ble_manager.queue_overflow_count = 0
