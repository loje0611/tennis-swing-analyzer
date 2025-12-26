import streamlit as st
import asyncio
import logging
from queue import Queue
from src.config import MAX_QUEUE_SIZE
from src.ble_manager import RealBLEManager
from src.ui import render_sidebar, render_connection_view, render_collection_view

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="Tennis Swing Logger",
    page_icon="🎾",
    layout="wide"
)

# --- 2. 세션 상태 초기화 ---
if 'view' not in st.session_state:
    st.session_state.view = 'connection'
if 'collection_state' not in st.session_state:
    st.session_state.collection_state = 'ready'
if 'recorded_data' not in st.session_state:
    st.session_state.recorded_data = []
if 'queue_overflow_count' not in st.session_state:
    st.session_state.queue_overflow_count = 0

# 큐 초기화
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = Queue(maxsize=MAX_QUEUE_SIZE)

def initialize_manager():
    # 기존 매니저가 있다면 정리
    if 'ble_manager' in st.session_state:
        st.session_state.ble_manager.stop()
    
    logger.info("Initializing RealBLEManager")
    st.session_state.ble_manager = RealBLEManager(st.session_state.data_queue)

# 매니저 초기화
if 'ble_manager' not in st.session_state:
    initialize_manager()

# 연결 해제 콜백 정의
def disconnect():
    if 'ble_manager' in st.session_state:
        st.session_state.ble_manager.stop()
    st.session_state.view = 'connection'
    st.session_state.collection_state = 'ready'
    st.session_state.recorded_data = []
    
    # 큐 비우기
    while not st.session_state.data_queue.empty():
        try:
            st.session_state.data_queue.get_nowait()
        except:
            break
    
    st.rerun()

st.session_state.disconnect_func = disconnect

# --- 4. 스캔 및 연결 함수 ---
def scan_and_connect():
    async def _scan_and_connect():
        success, message, device = await st.session_state.ble_manager.scan()
        if success:
            st.session_state.ble_manager.start_connection(device.address if device else "")
            # 연결 확인을 위해 잠시 대기
            await asyncio.sleep(1.0)
            if st.session_state.ble_manager.connected:
                return True, "연결 성공"
            else:
                return False, "연결 실패 (타임아웃 등)"
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

if st.session_state.view == 'connection':
    render_connection_view(scan_and_connect)
else:
    # 연결 끊김 체크 (리얼 모드일 때만 중요할 수 있으나, 목 모드도 simulating disconnect 가능)
    if not st.session_state.ble_manager.connected:
        st.warning("⚠️ 센서 연결이 끊어졌습니다.")
        if st.button("연결 대기 화면으로"):
            disconnect()
    else:
        render_collection_view()
