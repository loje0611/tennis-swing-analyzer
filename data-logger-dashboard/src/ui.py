import streamlit as st
import time
import subprocess
import pandas as pd
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
# Inference settings
# FIX: Reduced from 100 to 50 to match model input shape (300 features / 6 axes = 50 samples)
INFERENCE_WINDOW_SIZE = 50  # 1000ms at 50Hz
MODEL_PATH = "/home/keunu/tennis-swing-analyzer/model.eim"

# --- 1. 연결 객체 영속화 (Global Singleton) ---
@st.cache_resource
def get_cached_ble_manager():
    """
    RealBLEManager를 캐싱하여 세션 리로드 후에도 연결 객체를 유지.
    """
    print("Initializing RealBLEManager (Cached)")
    return RealBLEManager(Queue(maxsize=MAX_QUEUE_SIZE))

def init_session_state():
    # --- 2. UI 상태 자동 복구 (Auto-Recovery) ---
    # 가장 먼저 매니저를 가져옴
    if 'ble_manager' not in st.session_state:
        st.session_state.ble_manager = get_cached_ble_manager()
        st.session_state.data_queue = st.session_state.ble_manager.data_queue

    # 매니저가 이미 연결된 상태라면 -> 즉시 콜렉션 뷰로 복구
    if st.session_state.ble_manager.connected:
        if 'view' not in st.session_state or st.session_state.view != 'collection':
            st.session_state.view = 'collection'
            st.toast("🔄 기존 연결을 복구했습니다 (Auto-Recovered)", icon="🔗")
            # 필요 시 데이터 로깅 상태 등은 여기서 리셋하거나 유지 정책 결정
            # 여기서는 안전하게 로깅은 False로 시작
            st.session_state.is_logging = False

    # 기본 세션 초기화
    if 'view' not in st.session_state:
        st.session_state.view = 'connection'

    if 'vis_buffer' not in st.session_state:
        st.session_state.vis_buffer = deque(maxlen=VIS_BUFFER_SIZE)
    if 'log_buffer' not in st.session_state:
        st.session_state.log_buffer = []
    if 'is_logging' not in st.session_state:
        st.session_state.is_logging = False
    if 'collection_state' not in st.session_state:
        st.session_state.collection_state = 'ready' # ready, streaming
    if 'main_category' not in st.session_state:
        st.session_state.main_category = 'Forehand'
    if 'sub_category' not in st.session_state:
        st.session_state.sub_category = 'Flat'
    if 'last_data_time' not in st.session_state:
        st.session_state.last_data_time = datetime.now()
    if 'show_save_confirm' not in st.session_state:
        st.session_state.show_save_confirm = False
    
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
        st.session_state.inference_result = {"label": "Initializing...", "score": 0.0}

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ 설정")
        
        # Model Status
        if st.session_state.get('runner'):
            # Model loaded successfully
            st.success(f"🧠 AI 모델 로드됨")
        elif st.session_state.get('model_load_error'):
            # Model load failed
            st.error(f"❌ 모델 오류: {st.session_state.model_load_error}")
        else:
            # Not loaded yet or Library missing
            if ImpulseRunner is None:
                 st.warning("⚠️ Edge Impulse 라이브러리 부재")
            elif 'runner' not in st.session_state:
                 st.info("⏳ AI 모델 준비 중...")
            else:
                 # Library exists, keys exist, but runner is None and no error?
                 st.warning("⚠️ 모델 파일 없음 or 초기화 실패")

        status_text = "⚪ 센서 미연결"
        if st.session_state.get('ble_manager') and st.session_state.ble_manager.connected:
            if st.session_state.is_logging:
                status_text = "🔴 파일 저장 중 (Logging)"
                st.error(status_text)
            else:
                status_text = "🟢 데이터 수신 중 (Streaming)"
                st.success(status_text)
            
            # Check sensor status
            if hasattr(st.session_state.ble_manager, 'sensor_status'):
                 status = st.session_state.ble_manager.sensor_status
                 if status == 'error':
                     st.error("⚠️ 센서 데이터 수신 불가 (I2C 오류)")
        else:
            st.info(status_text)
        
        # 큐 상태 표시
        if 'data_queue' in st.session_state:
            queue_size = st.session_state.data_queue.qsize()
            queue_usage = (queue_size / MAX_QUEUE_SIZE) * 100
            st.caption(f"Buffer Usage: {queue_usage:.1f}% ({queue_size})")
        
        # 오버플로우 경고
        if st.session_state.get('ble_manager'):
             overflow = st.session_state.ble_manager.queue_overflow_count
             if overflow > 0:
                 st.warning(f"⚠️ 큐 오버플로우: {overflow}회")
        
        if st.session_state.get('ble_manager') and st.session_state.ble_manager.connected:
             # Regular Disconnect
             if st.button("연결 해제", type="secondary"):
                if 'disconnect_func' in st.session_state:
                    st.session_state.disconnect_func()
        
        # --- 3. 강제 연결 해제 버튼 (Emergency) ---
        st.markdown("---")
        with st.expander("🛠️ 문제 해결 (Troubleshooting)"):
            st.caption("화면이 멈추거나 연결이 꼬였을 때 사용하세요.")
            if st.button("🔄 블루투스 리셋 (Hard Reset)", type="primary"):
                st.cache_resource.clear()
                # Stop existing manager if possible
                if st.session_state.get('ble_manager'):
                     st.session_state.ble_manager.stop()
                st.rerun()

        st.markdown("---")

        # 📶 스마트 와이파이 설정
        with st.expander("WiFi 설정"):
            if st.button("🔄 와이파이 검색"):
                with st.spinner("주변 네트워크 검색 중..."):
                    try:
                        cmd = ["sudo", "nmcli", "-f", "SSID,SIGNAL,BARS", "device", "wifi", "list", "--rescan", "yes"]
                        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        
                        if result.returncode == 0:
                            networks = []
                            seen_ssids = set()
                            
                            lines = result.stdout.strip().split('\n')
                            if len(lines) > 1:
                                for line in lines[1:]:
                                    line = line.strip()
                                    if not line: continue
                                    parts = line.rsplit(None, 2) 
                                    
                                    if len(parts) >= 3:
                                        ssid = parts[0].strip()
                                        signal = parts[1].strip()
                                        bars = parts[2].strip()
                                        
                                        if ssid and ssid != "--" and ssid not in seen_ssids:
                                            try:
                                                sig_int = int(signal)
                                                networks.append({'SSID': ssid, 'SIGNAL': sig_int, 'BARS': bars})
                                                seen_ssids.add(ssid)
                                            except:
                                                pass
                            
                            networks.sort(key=lambda x: x['SIGNAL'], reverse=True)
                            st.session_state.wifi_networks = [f"{n['SSID']} ({n['BARS']})" for n in networks]
                            st.session_state.raw_wifi_networks = networks
                        else:
                            st.error("스캔 실패")
                    except Exception as e:
                        st.error(f"오류: {e}")

            wifi_options = st.session_state.get('wifi_networks', [])
            raw_networks = st.session_state.get('raw_wifi_networks', [])
            
            selected_wifi_str = st.selectbox("네트워크 선택", wifi_options)
            wifi_password = st.text_input("비밀번호", type="password")
            
            if st.button("연결하기"):
                if selected_wifi_str:
                    try:
                        index = wifi_options.index(selected_wifi_str)
                        target_ssid = raw_networks[index]['SSID']
                        
                        with st.spinner(f"'{target_ssid}'에 연결 중..."):
                            cmd = ["sudo", "nmcli", "device", "wifi", "connect", target_ssid, "password", wifi_password]
                            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            
                            if res.returncode == 0:
                                st.success(f"✅ '{target_ssid}' 연결 성공! IP가 변경될 수 있습니다.")
                            else:
                                st.error(f"❌ 연결 실패: {res.stderr}")
                    except ValueError:
                         st.error("네트워크 선택 오류")
                else:
                    st.warning("네트워크를 선택하세요.")

        # 🛑 안전 종료
        st.markdown("---")
        if st.button("시스템 종료", type="primary"):
             st.session_state.show_shutdown_confirm = True
        
        if st.session_state.get('show_shutdown_confirm', False):
            st.warning("⚠️ 정말로 시스템을 종료하시겠습니까?")
            col_sd1, col_sd2 = st.columns(2)
            with col_sd1:
                if st.button("예, 종료합니다"):
                    st.info("종료 중... 초록불이 꺼지면 전원을 분리하세요.")
                    subprocess.run(["sudo", "shutdown", "-h", "now"])
            with col_sd2:
                if st.button("취소"):
                    st.session_state.show_shutdown_confirm = False
                    st.rerun()

def render_connection_view(scan_callback):
    st.markdown("---")
    st.markdown("### 📡 센서 연결")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("📡 센서 찾기 및 연결", type="primary", use_container_width=True):
            with st.spinner("BLE 디바이스 스캔 중..."):
                scan_callback()
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption(f"서비스 UUID '{SERVICE_UUID}'를 가진 센서를 찾아 연결합니다.")

def process_data_queue():
    """Queue에서 데이터를 꺼내 버퍼에 저장"""
    if 'data_queue' in st.session_state:
        q = st.session_state.data_queue
        
        # 만약 로깅 중이 아니고 큐가 너무 많이 쌓였다면 (예: 브라우저 백그라운드 등)
        # 최신 데이터만 남기고 스킵하여 실시간성 확보
        if not st.session_state.is_logging and q.qsize() > 1000:
            skipped = 0
            while not q.empty():
                try:
                    q.get_nowait()
                    skipped += 1
                except:
                    break
            st.toast(f"⚠️ 지연된 데이터 {skipped}개 스킵됨 (Real-time Sync)")
            # 오버플로우 카운트 초기화 (UI 상의 혼란 방지)
            if st.session_state.get('ble_manager'):
                st.session_state.ble_manager.queue_overflow_count = 0
            return

        # 정상 처리
        # Batch Fetch Optimization
        # 큐에 있는 모든 데이터를 한 번에 가져와서 처리 (렌더링 횟수 감소)
        items = []
        while not q.empty():
            try:
                items.append(q.get_nowait())
            except:
                break
        
        if items:
            # Update last data time
            st.session_state.last_data_time = datetime.now()
            print(f"DEBUG: Processed {len(items)} items. Buffer size: {len(st.session_state.inference_buffer)}")
            
            # Visualization buffer
            st.session_state.vis_buffer.extend(items)
            
            if st.session_state.is_logging:
                st.session_state.log_buffer.extend(items)
            
            # Inference Buffer & Logic
            if st.session_state.get('runner'):
                for item in items:
                    # Append 6 axes in order: ax, ay, az, gx, gy, gz
                    st.session_state.inference_buffer.append([
                        item['accel_x'], item['accel_y'], item['accel_z'],
                        item['gyro_x'], item['gyro_y'], item['gyro_z']
                    ])
                
                # Run inference if we have enough data
                if len(st.session_state.inference_buffer) == INFERENCE_WINDOW_SIZE:
                    # Flatten the data for Edge Impulse
                    features = []
                    for sample in st.session_state.inference_buffer:
                        features.extend(sample)
                    
                    try:
                        # print(f"DEBUG: Running inference on {len(features)} features")
                        res = st.session_state.runner.classify(features)
                        
                        # Debugging: Print result randomly or periodically?
                        # Let's print only if score > 0.5 or every 10th time? 
                        # For now, just print everything to log
                        print(f"DEBUG: Inference Result: {res['result']}")

                        # res['result']['classification'] is a dict like {'label': score, ...}
                        if 'result' in res and 'classification' in res['result']:
                            classifications = res['result']['classification']
                            best_label = max(classifications, key=classifications.get)
                            best_score = classifications[best_label]
                            
                            st.session_state.inference_result = {
                                "label": best_label,
                                "score": best_score
                            }
                    except Exception as e:
                        print(f"Inference error: {e}")

            # Reset overflow count since we are consuming data
            if st.session_state.get('ble_manager'):
                st.session_state.ble_manager.queue_overflow_count = 0

# --- Live Dashboard Logic using st.fragment ---
# If fragment is available, use it to update only this part of the UI
if fragment:
    @fragment(run_every=0.1)
    def render_live_dashboard():
        process_data_queue()
        
        # --- Inference Result Display ---
        if 'inference_result' in st.session_state:
            result = st.session_state.inference_result
            label = result['label']
            score = result['score']
            
            # Display logic
            display_text = "..."
            display_color = "#999999"  # Gray (default/idle/low confidence)
            
            if score >= 0.7:
                display_text = label
                if label == "Forehand":
                    display_color = "#28a745"  # Green
                elif label == "Backhand":
                    display_color = "#007bff"  # Blue
                elif label == "Idle":
                    display_color = "#6c757d"  # Gray
            else:
                 display_text = "분석 중..."
            
            st.markdown(
                f"""
                <div style="
                    text-align: center; 
                    background-color: {display_color}22; 
                    padding: 20px; 
                    border-radius: 10px; 
                    border: 2px solid {display_color};
                    margin-bottom: 20px;">
                    <h3 style="margin: 0; color: {display_color};">Swing Analysis</h3>
                    <h1 style="margin: 0; font-size: 60px; color: {display_color}; font-weight: bold;">{display_text}</h1>
                    <p style="margin: 0; color: #666;">Confidence: {score*100:.1f}%</p>
                </div>
                """
            , unsafe_allow_html=True)
            
        # --- Logging Control (Moved inside fragment for real-time updates) ---
        col_log1, col_log2 = st.columns([2, 1])
        with col_log1:
            if st.session_state.is_logging:
                if st.session_state.get('show_save_confirm', False):
                    st.warning("⚠️ 정말로 데이터를 저장하시겠습니까?")
                    c_save, c_discard = st.columns(2)
                    with c_save:
                        if st.button("✅ 저장 (Save)", type="primary", use_container_width=True):
                             save_and_stop()
                    with c_discard:
                         st.markdown("") # Add spacing
                         if st.button("🗑️ 폐기 (Discard)", type="secondary", use_container_width=True):
                             discard_and_stop()
                else:
                     if st.button("💾 파일 저장 중지 (Stop Logging)", type="primary", use_container_width=True):
                         confirm_stop_logging()
            else:
                 if st.button("🔴 파일 저장 시작 (Start Logging)", use_container_width=True):
                     start_logging()
        
        with col_log2:
            if st.session_state.is_logging:
                st.markdown(f"**수집된 데이터:** {len(st.session_state.log_buffer)} 개")
            else:
                st.markdown("**대기 중...**")
        
        st.markdown("---")

        # --- Sensor Status Check (Switch OFF?) ---
        # 1초 이상 데이터가 없으면 Idle로 간주
        time_since_last = (datetime.now() - st.session_state.get('last_data_time', datetime.now())).total_seconds()
        is_idle = time_since_last > 1.0
        
        if is_idle:
            st.warning("⏸️ 센서 대기 중 (Switch OFF) - 데이터를 수신하지 못하고 있습니다.")

        # --- Live Visualization ---
        # Latest Values
        if st.session_state.vis_buffer:
            latest = st.session_state.vis_buffer[-1]
            
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Accel X", f"{latest['accel_x']:.2f}")
            c2.metric("Accel Y", f"{latest['accel_y']:.2f}")
            c3.metric("Accel Z", f"{latest['accel_z']:.2f}")
            c4.metric("Gyro X", f"{latest['gyro_x']:.0f}")
            c5.metric("Gyro Y", f"{latest['gyro_y']:.0f}")
            c6.metric("Gyro Z", f"{latest['gyro_z']:.0f}")
        
        # Charts
        tab1, tab2 = st.tabs(["📉 가속도 (Accel)", "🔄 자이로 (Gyro)"])
        
        if len(st.session_state.vis_buffer) > 0:
            df = pd.DataFrame(st.session_state.vis_buffer)
            
            with tab1:
                st.line_chart(df[['accel_x', 'accel_y', 'accel_z']])
            
            with tab2:
                st.line_chart(df[['gyro_x', 'gyro_y', 'gyro_z']])
        else:
            if not is_idle:
                st.info("데이터 수신 대기 중...")
else:
    # Fallback for older Streamlit versions (deprecated method using rerun)
    def render_live_dashboard():
        process_data_queue()
        
        # --- Inference Result Display (Fallback) ---
        if 'inference_result' in st.session_state:
            result = st.session_state.inference_result
            st.metric("AI Analysis", f"{result['label']} ({result['score']*100:.0f}%)")

        st.markdown("---")
        
        # --- Logging Control ---
        col_log1, col_log2 = st.columns([2, 1])
        with col_log1:
            if st.session_state.is_logging:
                if st.session_state.get('show_save_confirm', False):
                    st.warning("⚠️ 정말로 데이터를 저장하시겠습니까?")
                    c_save, c_discard = st.columns(2)
                    with c_save:
                        if st.button("✅ 저장 (Save)", type="primary", use_container_width=True):
                             save_and_stop()
                    with c_discard:
                         if st.button("🗑️ 폐기 (Discard)", type="secondary", use_container_width=True):
                             discard_and_stop()
                else:
                     if st.button("💾 파일 저장 중지 (Stop Logging)", type="primary", use_container_width=True):
                         confirm_stop_logging()
            else:
                 if st.button("🔴 파일 저장 시작 (Start Logging)", use_container_width=True):
                      start_logging()
        
        with col_log2:
            if st.session_state.is_logging:
                st.markdown(f"**수집된 데이터:** {len(st.session_state.log_buffer)} 개")
            else:
                st.markdown("**대기 중...**")
        
        # ... logic ... (Simplified fallback)
        st.warning("⚠️ Streamlit 버전이 낮아 'st.fragment'를 사용할 수 없습니다. 그래프 중복이 발생할 수 있습니다.")
        time.sleep(0.1)
        st.rerun()

def render_collection_view():
    init_session_state()
    
    # --- Top Controls ---
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.main_category = st.selectbox(
            "대분류", ["Forehand", "Backhand"], key="main_cat",
            index=0 if st.session_state.get('main_category') == 'Forehand' else 1
        )
    with col2:
        options = ["Flat", "Topspin", "Slice"]
        try:
            idx = options.index(st.session_state.get('sub_category', 'Flat'))
        except:
            idx = 0
        st.session_state.sub_category = st.selectbox(
            "소분류", options, key="sub_cat", index=idx
        )
    
    st.markdown("---")
    
    # Calling the fragment loop here
    # This will render the charts and auto-update ONLY this part
    render_live_dashboard()

def start_logging():
    st.session_state.is_logging = True
    st.session_state.log_buffer = []
    st.session_state.show_save_confirm = False
    pass 
    
def confirm_stop_logging():
    st.session_state.show_save_confirm = True

def save_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    
    if st.session_state.log_buffer:
        try:
            filepath = save_data_to_csv(
                st.session_state.log_buffer,
                st.session_state.main_category,
                st.session_state.sub_category
            )
            st.success(f"✅ 데이터 저장 완료: {filepath}")
            st.toast(f"File saved: {filepath}")
        except Exception as e:
            st.error(f"저장 오류: {e}")
    else:
        st.warning("저장할 데이터가 없습니다.")
    st.rerun()

def discard_and_stop():
    st.session_state.is_logging = False
    st.session_state.show_save_confirm = False
    st.session_state.log_buffer = []
    st.toast("🗑️ 데이터가 폐기되었습니다.")
    st.rerun()
