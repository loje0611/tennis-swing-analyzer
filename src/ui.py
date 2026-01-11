import streamlit as st
import time
from src.config import MAX_QUEUE_SIZE, SERVICE_UUID
from src.data_manager import save_data_to_csv

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ 설정")
        
        if st.session_state.view == 'collection':
            st.info("🟢 센서 연결됨")
            
            # 큐 상태 표시
            if 'data_queue' in st.session_state:
                queue_size = st.session_state.data_queue.qsize()
                queue_usage = (queue_size / MAX_QUEUE_SIZE) * 100
                st.metric("큐 사용률", f"{queue_usage:.1f}%", f"{queue_size}/{MAX_QUEUE_SIZE}")
            
            # 오버플로우 경고
            overflow = st.session_state.get('queue_overflow_count', 0)
            if overflow > 0:
                st.warning(f"⚠️ 큐 오버플로우: {overflow}회")
            
            if st.button("연결 해제", type="secondary"):
                # Callback to disconnect
                if 'disconnect_func' in st.session_state:
                    st.session_state.disconnect_func()
        else:
            st.info("⚪ 센서 미연결")

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

def render_collection_view():
    if st.session_state.collection_state == 'ready':
        _render_ready_state()
    elif st.session_state.collection_state == 'recording':
        _render_recording_state()
    elif st.session_state.collection_state == 'review':
        _render_review_state()

def _render_ready_state():
    st.markdown("---")
    st.markdown("### 📝 녹화 준비")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.main_category = st.selectbox(
            "대분류",
            ["Forehand", "Backhand"],
            key="main_cat",
            index=0 if st.session_state.get('main_category') == 'Forehand' else 1
        )
    
    with col2:
        # Pre-select based on session state if needed, or default
        options = ["Flat", "Topspin", "Slice"]
        try:
            idx = options.index(st.session_state.get('sub_category', 'Flat'))
        except:
            idx = 0
            
        st.session_state.sub_category = st.selectbox(
            "소분류",
            options,
            key="sub_cat",
            index=idx
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔴 녹화 시작", type="primary", use_container_width=True):
            st.session_state.collection_state = 'recording'
            st.session_state.recorded_data = []
            st.rerun()

def _render_recording_state():
    st.markdown("---")
    st.markdown("### 🔴 녹화 중")
    
    # 데이터 수집 (UI 렌더링 시 큐에서 꺼냄)
    if 'data_queue' in st.session_state:
        while not st.session_state.data_queue.empty():
            try:
                data_point = st.session_state.data_queue.get_nowait()
                st.session_state.recorded_data.append(data_point)
            except Exception:
                break
    
    data_count = len(st.session_state.recorded_data)
    st.info(f"데이터 수집 중... (현재 {data_count}개)")
    
    # 큐 상태가 꽉 찼는지 확인하여 경고 줄 수도 있음
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("⬛ 녹화 중지", type="primary", use_container_width=True):
            st.session_state.collection_state = 'review'
            st.rerun()
            
    # 자동 리런 for UI update
    time.sleep(0.1)
    st.rerun()

def _render_review_state():
    st.markdown("---")
    st.markdown("### 📊 녹화 완료")
    
    data_count = len(st.session_state.recorded_data)
    st.info(f"총 {data_count}개의 데이터가 수집되었습니다.")
    
    if data_count > 0:
        with st.expander("데이터 미리보기"):
            preview_data = st.session_state.recorded_data[:10]
            for i, data in enumerate(preview_data):
                st.text(f"{i+1}. {data['timestamp'].strftime('%H:%M:%S.%f')[:-3]} - "
                       f"Accel: ({data['accel_x']:.2f}, {data['accel_y']:.2f}, {data['accel_z']:.2f})")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 저장 (Save)", type="primary", use_container_width=True):
            try:
                filepath = save_data_to_csv(
                    st.session_state.recorded_data,
                    st.session_state.main_category,
                    st.session_state.sub_category
                )
                st.success(f"✅ 데이터가 저장되었습니다: {filepath}")
                st.session_state.collection_state = 'ready'
                st.session_state.recorded_data = []
                # Don't rerun immediately to let user see success message
            except Exception as e:
                st.error(f"저장 오류: {e}")
    
    with col2:
        if st.button("🗑️ 폐기 (Discard)", type="secondary", use_container_width=True):
            st.session_state.collection_state = 'ready'
            st.session_state.recorded_data = []
            st.rerun()
