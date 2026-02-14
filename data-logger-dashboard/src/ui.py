import streamlit as st
import time
import subprocess
import pandas as pd
from collections import deque
from datetime import datetime
from src.config import MAX_QUEUE_SIZE, SERVICE_UUID
from src.data_manager import save_data_to_csv

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

def init_session_state():
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

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ 설정")
        
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
             if st.button("연결 해제", type="secondary"):
                if 'disconnect_func' in st.session_state:
                    st.session_state.disconnect_func()

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
            
            # Visualization Buffer (Extend)
            st.session_state.vis_buffer.extend(items)
            
            if st.session_state.is_logging:
                st.session_state.log_buffer.extend(items)
            
            # Reset overflow count since we are consuming data
            if st.session_state.get('ble_manager'):
                st.session_state.ble_manager.queue_overflow_count = 0

# --- Live Dashboard Logic using st.fragment ---
# If fragment is available, use it to update only this part of the UI
if fragment:
    @fragment(run_every=0.1)
    def render_live_dashboard():
        process_data_queue()
        
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
