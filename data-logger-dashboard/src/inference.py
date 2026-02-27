import streamlit as st
import math
import time
from collections import deque
from datetime import datetime
from src.config import (
    PEAK_ACCEL_THRESHOLD_G,
    PEAK_COOLDOWN_SEC,
    PACING_DELAY_SEC,
    INFERENCE_PEAK_THRESHOLD_G,
    INFERENCE_FALSE_POSITIVE_G,
    INFERENCE_WINDOW_SAMPLES,
    INFERENCE_BUFFER_SIZE,
    INFERENCE_FUTURE_SAMPLES,
    INFERENCE_COOLDOWN_FRAMES,
    SWING_CONFIDENCE_THRESHOLD,
    RACKET_RADIUS_M,
    SPEED_CALIBRATION_FACTOR,
    SPEED_HISTORY_WINDOW_SEC,
)


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
        try:
            item = q.get_nowait()
            if st.session_state.get('is_logging', False):
                packet_count = st.session_state.get('logging_packet_count', 0)
                item['timestamp_ms'] = packet_count * 20
                st.session_state.logging_packet_count = packet_count + 1
            items.append(item)
        except Exception: break
    
    if not items:
        return

    st.session_state.last_data_time = datetime.now()
    
    # --- Speed Calculation (Physics: V = r * omega) ---
    last_item = items[-1]
    gx, gy, gz = last_item['gyro_x'], last_item['gyro_y'], last_item['gyro_z']
    gyro_mag = math.sqrt(gx**2 + gy**2 + gz**2)  # deg/s
    rad_s = math.radians(gyro_mag)
    v_mps = RACKET_RADIUS_M * rad_s
    v_kmh = v_mps * 3.6 * SPEED_CALIBRATION_FACTOR
    st.session_state.current_speed_kmh = v_kmh

    # --- Data Logger Logic (Peak Detection & Pacing) ---
    current_time = time.time()
    
    # 1. Peak Detection
    max_accel_mag = 0.0
    for item in items:
        mag = math.sqrt(item['accel_x']**2 + item['accel_y']**2 + item['accel_z']**2)
        if mag > max_accel_mag:
            max_accel_mag = mag
            
    st.session_state.last_max_mag = max_accel_mag

    if max_accel_mag >= PEAK_ACCEL_THRESHOLD_G:
        if current_time - st.session_state.last_peak_time >= PEAK_COOLDOWN_SEC:
            st.session_state.last_peak_time = current_time
            st.session_state.pacing_guide_triggered = False
            
            if st.session_state.is_logging:
                st.session_state.session_peak_count = st.session_state.get('session_peak_count', 0) + 1
            
            print(f"Peak Detected: {max_accel_mag:.2f} G")
            
    # 2. Pacing Assistant
    if st.session_state.is_logging:
        if not st.session_state.pacing_guide_triggered:
            if current_time - st.session_state.last_peak_time >= PACING_DELAY_SEC:
                st.session_state.tts_message = "다음"
                st.session_state.tts_swing_id = f"pace_{current_time}"
                st.session_state.pacing_guide_triggered = True

    # --- Peak Speed History for Gauge Display ---
    now = datetime.now()
    st.session_state.speed_history.append((now, v_kmh))
    
    while st.session_state.speed_history and (now - st.session_state.speed_history[0][0]).total_seconds() > SPEED_HISTORY_WINDOW_SEC:
        st.session_state.speed_history.popleft()
    
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
        if getattr(st.session_state.inference_buffer, "maxlen", 0) < INFERENCE_BUFFER_SIZE:
            old_data = list(st.session_state.inference_buffer)
            st.session_state.inference_buffer = deque(old_data, maxlen=INFERENCE_BUFFER_SIZE)

        if 'inference_sm_state' not in st.session_state:
            st.session_state.inference_sm_state = 'WAITING_FOR_PEAK'
            st.session_state.samples_after_peak = 0
            st.session_state.cooldown_frames = 0

        for item in items:
            features = [
                item['accel_x'], item['accel_y'], item['accel_z'],
                item['gyro_x'], item['gyro_y'], item['gyro_z']
            ]
            st.session_state.inference_buffer.append(features)
            
            # --- State Machine: 피크(Impact) 감지 및 정렬 ---
            if st.session_state.inference_sm_state == 'COOLDOWN':
                st.session_state.cooldown_frames -= 1
                if st.session_state.cooldown_frames <= 0:
                    st.session_state.inference_sm_state = 'WAITING_FOR_PEAK'
                    
            elif st.session_state.inference_sm_state == 'WAITING_FOR_PEAK':
                accel_mag = math.sqrt(item['accel_x']**2 + item['accel_y']**2 + item['accel_z']**2)
                if accel_mag > INFERENCE_PEAK_THRESHOLD_G:
                    print(f"Inference SM: Peak detected! magnitude={accel_mag:.2f}")
                    st.session_state.inference_sm_state = 'WAITING_FOR_FUTURE_SAMPLES'
                    st.session_state.samples_after_peak = 0
                    
            elif st.session_state.inference_sm_state == 'WAITING_FOR_FUTURE_SAMPLES':
                st.session_state.samples_after_peak += 1
                if st.session_state.samples_after_peak >= INFERENCE_FUTURE_SAMPLES:
                    if len(st.session_state.inference_buffer) >= INFERENCE_WINDOW_SAMPLES:
                        window_features = list(st.session_state.inference_buffer)[-INFERENCE_WINDOW_SAMPLES:]
                        
                        # Validate: reject false positives (e.g. dropping racket)
                        max_mag = 0
                        for row in window_features:
                            ax, ay, az = row[0], row[1], row[2]
                            mag = math.sqrt(ax**2 + ay**2 + az**2)
                            if mag > max_mag:
                                max_mag = mag
                                
                        if max_mag < INFERENCE_FALSE_POSITIVE_G:
                            print(f"Inference SM: False positive peak detected (max_mag={max_mag:.2f}). Ignoring.")
                            st.session_state.inference_sm_state = 'WAITING_FOR_PEAK'
                            continue
                            
                        print(f"Slicing {INFERENCE_WINDOW_SAMPLES} samples from buffer of length {len(st.session_state.inference_buffer)}")
                        
                        flat_features = []
                        for row in window_features:
                            flat_features.extend(row)
                            
                        try:
                            print(f"Running classify with features length {len(flat_features)}")
                            res = st.session_state.runner.classify(flat_features)
                            print(f"Classify result: {res}")
                            st.session_state.inference_error = None
                            if 'result' in res and 'classification' in res['result']:
                                classifications = res['result']['classification']
                                best_label = max(classifications, key=classifications.get)
                                best_score = classifications[best_label]
                                
                                st.session_state.inference_result = {
                                    "label": best_label,
                                    "score": best_score
                                }
                                st.session_state.inference_probabilities = dict(classifications)

                                # --- 스윙 카운팅 및 UI 업데이트 ---
                                if best_score > SWING_CONFIDENCE_THRESHOLD:
                                    display_label = best_label.replace("_", " ")

                                    if "Forehand" in best_label:
                                        st.session_state.swing_count_fh += 1
                                        st.session_state.last_swing_speed = st.session_state.peak_speed_2s
                                        st.session_state.last_swing_type = display_label
                                        st.session_state.force_gauge_update = True
                                        st.session_state.recent_shots.append(("FH", st.session_state.peak_speed_2s))
                                        
                                        if st.session_state.active_page == "🔥 Live Coaching":
                                            speed = int(st.session_state.peak_speed_2s)
                                            st.session_state.tts_message = f"{display_label}, {speed} 킬로미터"
                                            st.session_state.tts_swing_id = f"fh_{st.session_state.swing_count_fh}_{time.time()}"
                                        
                                    elif "Backhand" in best_label:
                                        st.session_state.swing_count_bh += 1
                                        st.session_state.last_swing_speed = st.session_state.peak_speed_2s
                                        st.session_state.last_swing_type = display_label
                                        st.session_state.force_gauge_update = True
                                        st.session_state.recent_shots.append(("BH", st.session_state.peak_speed_2s))
                                        
                                        if st.session_state.active_page == "🔥 Live Coaching":
                                            speed = int(st.session_state.peak_speed_2s)
                                            st.session_state.tts_message = f"{display_label}, {speed} 킬로미터"
                                            st.session_state.tts_swing_id = f"bh_{st.session_state.swing_count_bh}_{time.time()}"
                                    
                                    st.session_state.last_predicted_label = best_label

                        except Exception as e:
                            st.session_state.inference_error = str(e)
                            print(f"Inference error: {e}")
                        
                        st.session_state.inference_sm_state = 'COOLDOWN'
                        st.session_state.cooldown_frames = INFERENCE_COOLDOWN_FRAMES
                    else:
                        st.session_state.inference_sm_state = 'WAITING_FOR_PEAK'

        st.session_state.inference_debug_buffer_len = len(st.session_state.inference_buffer)
