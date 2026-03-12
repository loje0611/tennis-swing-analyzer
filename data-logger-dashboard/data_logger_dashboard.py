import streamlit as st
import asyncio
import logging
from datetime import datetime
from src.ble_manager import RealBLEManager
from src.ui import render_sidebar, render_connection_view, render_collection_view, render_global_header
from src.tts import render_tts_listener
from src.state import init_session_state

# Early initialization of session state to load models
# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="Tennis Swing Analyzer",
    page_icon="🎾",
    layout="wide"
)

# --- 2. 세션 상태 초기화 ---
init_session_state()

# --- 3. 로깅 설정 ---
logging.basicConfig(level=logging.INFO)

# --- 4. 스캔 및 연결 함수 ---
def scan_and_connect():
    async def _scan_and_connect():
        success, message, device = await st.session_state.ble_manager.scan()
        if success:
            st.session_state.ble_manager.start_connection(device.address if device else "")
            # 연결 확인을 위해 대기 (최대 5초)
            for _ in range(10):
                await asyncio.sleep(0.5)
                if st.session_state.ble_manager.connected:
                    return True, "연결 성공"
                
                # Check for explicit error
                if st.session_state.ble_manager.last_error:
                    return False, f"연결 오류: {st.session_state.ble_manager.last_error}"
            
            return False, "연결 실패 (타임아웃: 5초 경과)"
        else:
            return False, message

    # 새 이벤트 루프에서 실행
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success, message = loop.run_until_complete(_scan_and_connect())
        if success:
            st.success("🟢 연결됨!")
            st.session_state.view = 'collection'
            st.rerun()
        else:
            st.error(f"❌ {message}")
    finally:
        loop.close()

# --- 5. UI 렌더링 ---
render_sidebar()
render_global_header()

# Fallback safety check
if 'view' not in st.session_state:
    print("WARNING: 'view' was missing in session_state. Forcing initialization.")
    st.session_state.view = 'connection'

if st.session_state.view == 'connection':
    render_connection_view(scan_and_connect)
else:
    if not st.session_state.ble_manager.connected:
        st.warning("⚠️ 센서 연결이 끊어졌습니다. 사이드바에서 연결 화면으로 이동하거나 기기를 다시 연결해 주세요.")
    else:
        # Watchdog: 상단 붉은색 경고 (2초 이상 데이터 없음 / ERR:NO_SENSOR)
        last_data = st.session_state.get("last_data_time")
        timeout_sec = 2.0
        if st.session_state.ble_manager.sensor_status == "error":
            st.error("🔴 **센서 오류**: MPU6050이 감지되지 않습니다 (ERR:NO_SENSOR). 배선을 확인해 주세요.")
        elif last_data and (datetime.now() - last_data).total_seconds() > timeout_sec:
            st.error("🔴 **BLE 타임아웃**: 2초 이상 센서 데이터가 없습니다. 연결을 확인하거나 재연결해 주세요.")
        render_collection_view()
        render_tts_listener()
