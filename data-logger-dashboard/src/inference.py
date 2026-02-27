import streamlit as st
import numpy as np
import math
import time
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
    
    # --- Speed Calculation (Physics) ---
    RACKET_RADIUS_M = 1.1        # Effective radius of arm + racket
    CALIBRATION_FACTOR = 1.2     # Calibration factor for air resistance etc.
    
    # V = r * omega
    last_item = items[-1]
    gx, gy, gz = last_item['gyro_x'], last_item['gyro_y'], last_item['gyro_z']
    gyro_mag = np.sqrt(gx**2 + gy**2 + gz**2)  # deg/s
    rad_s = math.radians(gyro_mag)
    v_mps = RACKET_RADIUS_M * rad_s
    v_kmh = v_mps * 3.6 * CALIBRATION_FACTOR
    st.session_state.current_speed_kmh = v_kmh

    # --- Data Logger Logic (Peak Detection & Pacing) ---
    current_time = time.time()
    
    # 1. Peak Detection (> 5.0G, 1.5s cooldown) - INCREASED THRESHOLD
    # Check if ANY sample in the batch exceeds the threshold
    max_accel_mag = 0.0
    for item in items:
        mag = math.sqrt(item['accel_x']**2 + item['accel_y']**2 + item['accel_z']**2)
        if mag > max_accel_mag:
            max_accel_mag = mag
            
    # For Debugging
    st.session_state.last_max_mag = max_accel_mag

    if max_accel_mag >= 3.0:
        if current_time - st.session_state.last_peak_time >= 1.5:
            st.session_state.last_peak_time = current_time
            st.session_state.pacing_guide_triggered = False
            
            # Count peaks for Data Logger session stats
            if st.session_state.is_logging:
                st.session_state.session_peak_count = st.session_state.get('session_peak_count', 0) + 1
            
            # Peak detected debugging
            print(f"Peak Detected: {max_accel_mag:.2f} G")
            
    # 2. Pacing Assistant (2.0s after peak)
    if st.session_state.is_logging:
        if not st.session_state.pacing_guide_triggered:
            if current_time - st.session_state.last_peak_time >= 2.0:
                st.session_state.tts_message = "다음"
                st.session_state.tts_swing_id = f"pace_{current_time}"
                st.session_state.pacing_guide_triggered = True

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
        # 1. 넉넉한 버퍼 유지 (3~4초 분량, 200샘플 확보)
        from collections import deque
        if getattr(st.session_state.inference_buffer, "maxlen", 0) < 200:
            old_data = list(st.session_state.inference_buffer)
            st.session_state.inference_buffer = deque(old_data, maxlen=200)

        # 상태 머신 변수 초기화
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
                # 5. 쿨타임 (중복 추론 방지)
                st.session_state.cooldown_frames -= 1
                if st.session_state.cooldown_frames <= 0:
                    st.session_state.inference_sm_state = 'WAITING_FOR_PEAK'
                    
            elif st.session_state.inference_sm_state == 'WAITING_FOR_PEAK':
                # 2. 피크 감지 (가속도 크기계산)
                accel_mag = math.sqrt(item['accel_x']**2 + item['accel_y']**2 + item['accel_z']**2)
                if accel_mag > 3.0:  # 임계치(Threshold)
                    st.session_state.inference_sm_state = 'WAITING_FOR_CENTERING'
                    st.session_state.samples_after_peak = 0
                    
            elif st.session_state.inference_sm_state == 'WAITING_FOR_CENTERING':
                # 3. 센터링 및 캡처 대기 (팔로스루 1초 대기 = 50Hz 기준 50샘플)
                st.session_state.samples_after_peak += 1
                if st.session_state.samples_after_peak >= 50:
                    # 4. 완벽한 2초 추출 (피크를 정가운데에 배치하기 위해 맨 뒤 100샘플Slice)
                    if len(st.session_state.inference_buffer) >= 100:
                        window_features = list(st.session_state.inference_buffer)[-100:]
                        
                        flat_features = []
                        for row in window_features:
                            flat_features.extend(row)
                            
                        # 추론 실행
                        try:
                            res = st.session_state.runner.classify(flat_features)
                            st.session_state.inference_error = None
                            if 'result' in res and 'classification' in res['result']:
                                classifications = res['result']['classification']
                                best_label = max(classifications, key=classifications.get)
                                best_score = classifications[best_label]
                                
                                st.session_state.inference_result = {
                                    "label": best_label,
                                    "score": best_score
                                }
                                st.session_state.inference_probabilities = classifications

                                # --- 스윙 카운팅 및 UI 업데이트 (이벤트 단발성 호출) ---
                                if best_score > 0.60:
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
                        
                        # 5. 쿨타임 (1.5초 = 50Hz 기준 75프레임 적용하여 중복 추론 방지)
                        st.session_state.inference_sm_state = 'COOLDOWN'
                        st.session_state.cooldown_frames = 75
                    else:
                        # 버퍼 사이즈가 모자란 특수 케이스 예외 처리
                        st.session_state.inference_sm_state = 'WAITING_FOR_PEAK'

        st.session_state.inference_debug_buffer_len = len(st.session_state.inference_buffer)

    if st.session_state.get('ble_manager'):
        st.session_state.ble_manager.queue_overflow_count = 0
