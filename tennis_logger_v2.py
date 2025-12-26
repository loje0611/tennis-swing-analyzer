import streamlit as st
import asyncio
import threading
from bleak import BleakScanner, BleakClient
from datetime import datetime
import csv
import os
from queue import Queue
from typing import Optional, List, Dict
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 상수 정의 ---
TARGET_DEVICE_NAME = "Tennis_Sensor_V1"
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DATA_FOLDER = "data"

# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="Tennis Swing Logger V2",
    page_icon="🎾",
    layout="wide"
)

# --- 2. 세션 상태 초기화 ---
if 'view' not in st.session_state:
    st.session_state.view = 'connection'  # 'connection' 또는 'collection'
if 'ble_client' not in st.session_state:
    st.session_state.ble_client = None
if 'ble_connected' not in st.session_state:
    st.session_state.ble_connected = False
if 'ble_thread' not in st.session_state:
    st.session_state.ble_thread = None
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = Queue()
if 'collection_state' not in st.session_state:
    st.session_state.collection_state = 'ready'  # 'ready', 'recording', 'review'
if 'recorded_data' not in st.session_state:
    st.session_state.recorded_data = []
if 'main_category' not in st.session_state:
    st.session_state.main_category = 'Forehand'
if 'sub_category' not in st.session_state:
    st.session_state.sub_category = 'Flat'

# --- 3. BLE 연결 관리 클래스 ---
class BLEClientManager:
    """BLE 클라이언트와 데이터 수집을 관리하는 클래스"""
    
    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.data_queue = Queue()
    
    def start_connection(self, address: str):
        """BLE 연결을 시작하고 백그라운드 스레드에서 데이터 수집 시작"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_async_loop, args=(address,), daemon=True)
        self.thread.start()
    
    def _run_async_loop(self, address: str):
        """별도 스레드에서 실행되는 asyncio 루프"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect_and_collect(address))
        except Exception as e:
            logger.error(f"BLE 루프 오류: {e}")
        finally:
            self.loop.close()
    
    async def _connect_and_collect(self, address: str):
        """BLE 연결 및 데이터 수집"""
        try:
            self.client = BleakClient(address)
            await self.client.connect()
            logger.info(f"BLE 연결 성공: {address}")
            st.session_state.ble_connected = True
            
            # Notification 핸들러 설정
            def notification_handler(sender, data: bytearray):
                """BLE 데이터 수신 핸들러"""
                try:
                    # 데이터 파싱 (예: "accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z" 형식)
                    decoded = data.decode('utf-8').strip()
                    parts = decoded.split(',')
                    if len(parts) == 6:
                        timestamp = datetime.now()
                        data_point = {
                            'timestamp': timestamp,
                            'accel_x': float(parts[0]),
                            'accel_y': float(parts[1]),
                            'accel_z': float(parts[2]),
                            'gyro_x': float(parts[3]),
                            'gyro_y': float(parts[4]),
                            'gyro_z': float(parts[5])
                        }
                        # 데이터를 큐에 추가 (녹화 상태는 메인 스레드에서 확인)
                        self.data_queue.put(data_point)
                        st.session_state.data_queue.put(data_point)
                except Exception as e:
                    logger.warning(f"데이터 파싱 오류: {e}")
            
            # Notification 시작
            await self.client.start_notify(CHARACTERISTIC_UUID, notification_handler)
            logger.info("Notification 시작됨")
            
            # 연결 유지
            while self.running and self.client.is_connected:
                await asyncio.sleep(0.1)
            
            # Notification 중지
            if self.client.is_connected:
                await self.client.stop_notify(CHARACTERISTIC_UUID)
                await self.client.disconnect()
            
        except Exception as e:
            logger.error(f"BLE 연결/수집 오류: {e}")
            st.session_state.ble_connected = False
        finally:
            if self.client and self.client.is_connected:
                try:
                    await self.client.disconnect()
                except:
                    pass
    
    def stop(self):
        """BLE 연결 중지"""
        self.running = False
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(lambda: None)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

# 전역 BLE 매니저 인스턴스
if 'ble_manager' not in st.session_state:
    st.session_state.ble_manager = BLEClientManager()

# --- 4. BLE 스캔 및 연결 함수 ---
def scan_and_connect():
    """BLE 디바이스를 스캔하고 연결"""
    async def _scan_and_connect():
        try:
            # BLE 디바이스 스캔
            devices = await BleakScanner.discover(timeout=5.0)
            
            # "Tennis_Sensor_V1" 디바이스 찾기
            target_device = None
            for device in devices:
                if device.name == TARGET_DEVICE_NAME:
                    target_device = device
                    break
            
            if target_device is None:
                return False, "Tennis_Sensor_V1 디바이스를 찾을 수 없습니다."
            
            # 연결 시도
            st.session_state.ble_manager.start_connection(target_device.address)
            
            # 연결 확인을 위해 잠시 대기
            await asyncio.sleep(1.0)
            
            if st.session_state.ble_connected:
                return True, "연결 성공"
            else:
                return False, "연결 실패"
                
        except Exception as e:
            logger.error(f"스캔/연결 오류: {e}")
            return False, f"오류: {str(e)}"
    
    # 새 이벤트 루프에서 실행
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success, message = loop.run_until_complete(_scan_and_connect())
        return success, message
    finally:
        loop.close()

# --- 5. 파일 저장 함수 ---
def save_data_to_csv(data: List[Dict], main_category: str, sub_category: str):
    """데이터를 CSV 파일로 저장"""
    # data 폴더 생성
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    # 파일명 생성: YYYYMMDD_HHMMSS_{Main}_{Sub}.csv
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{main_category}_{sub_category}.csv"
    filepath = os.path.join(DATA_FOLDER, filename)
    
    # CSV 파일 작성
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['timestamp', 'accel_x', 'accel_y', 'accel_z', 'gyro_x', 'gyro_y', 'gyro_z']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in data:
            writer.writerow({
                'timestamp': row['timestamp'].isoformat(),
                'accel_x': row['accel_x'],
                'accel_y': row['accel_y'],
                'accel_z': row['accel_z'],
                'gyro_x': row['gyro_x'],
                'gyro_y': row['gyro_y'],
                'gyro_z': row['gyro_z']
            })
    
    return filepath

# --- 6. 연결 해제 함수 ---
def disconnect_sensor():
    """센서 연결 해제"""
    st.session_state.ble_manager.stop()
    st.session_state.ble_client = None
    st.session_state.ble_connected = False
    st.session_state.view = 'connection'
    st.session_state.collection_state = 'ready'
    st.session_state.recorded_data = []
    st.rerun()

# --- 7. 메인 UI ---
st.title("🎾 Tennis Swing Logger V2")
st.markdown("#### 테니스 스윙 데이터 수집 도구")

# 사이드바
with st.sidebar:
    st.title("⚙️ 설정")
    
    if st.session_state.view == 'collection':
        st.info("🟢 센서 연결됨")
        if st.button("연결 해제", type="secondary"):
            disconnect_sensor()
    else:
        st.info("⚪ 센서 미연결")

# --- 8. 뷰별 화면 구성 ---
if st.session_state.view == 'connection':
    # === 1단계: 연결 대기 화면 ===
    st.markdown("---")
    st.markdown("### 📡 센서 연결")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📡 센서 찾기 및 연결", type="primary", use_container_width=True):
            with st.spinner("BLE 디바이스 스캔 중..."):
                success, message = scan_and_connect()
                
                if success:
                    st.success("🟢 센서 연결됨!")
                    st.session_state.view = 'collection'
                    st.rerun()
                else:
                    st.error(f"❌ {message}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("'Tennis_Sensor_V1' 디바이스를 찾아 연결합니다.")

else:
    # === 2단계: 데이터 수집 화면 ===
    
    if st.session_state.collection_state == 'ready':
        # A. 준비 상태
        st.markdown("---")
        st.markdown("### 📝 녹화 준비")
        
        col1, col2 = st.columns(2)
        with col1:
            main_category = st.selectbox(
                "대분류",
                ["Forehand", "Backhand"],
                key="main_cat"
            )
            st.session_state.main_category = main_category
        
        with col2:
            sub_category = st.selectbox(
                "소분류",
                ["Flat", "Topspin", "Slice"],
                key="sub_cat"
            )
            st.session_state.sub_category = sub_category
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔴 녹화 시작", type="primary", use_container_width=True):
                st.session_state.collection_state = 'recording'
                st.session_state.recorded_data = []
                st.rerun()
    
    elif st.session_state.collection_state == 'recording':
        # B. 녹화 중 상태
        st.markdown("---")
        st.markdown("### 🔴 녹화 중")
        
        # 큐에서 데이터 수집 (녹화 중일 때만)
        collected_count = 0
        while not st.session_state.data_queue.empty():
            try:
                data_point = st.session_state.data_queue.get_nowait()
                st.session_state.recorded_data.append(data_point)
                collected_count += 1
            except:
                break
        
        data_count = len(st.session_state.recorded_data)
        st.info(f"데이터 수집 중... (현재 {data_count}개)")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("⬛ 녹화 중지", type="primary", use_container_width=True):
                st.session_state.collection_state = 'review'
                st.rerun()
    
    elif st.session_state.collection_state == 'review':
        # C. 검토 상태
        st.markdown("---")
        st.markdown("### 📊 녹화 완료")
        
        data_count = len(st.session_state.recorded_data)
        st.info(f"총 {data_count}개의 데이터가 수집되었습니다.")
        
        # 데이터 미리보기 (선택사항)
        if data_count > 0:
            with st.expander("데이터 미리보기"):
                preview_data = st.session_state.recorded_data[:10]  # 처음 10개만
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
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 오류: {e}")
        
        with col2:
            if st.button("🗑️ 폐기 (Discard)", type="secondary", use_container_width=True):
                st.session_state.collection_state = 'ready'
                st.session_state.recorded_data = []
                st.rerun()

# --- 9. 자동 새로고침 (녹화 중일 때) ---
if st.session_state.collection_state == 'recording':
    import time
    time.sleep(0.1)  # 짧은 대기 (UI 업데이트를 위한)
    st.rerun()

# --- 10. 연결 상태 모니터링 ---
# BLE 연결이 끊어졌는지 확인
if st.session_state.view == 'collection' and not st.session_state.ble_connected:
    st.warning("⚠️ 센서 연결이 끊어졌습니다. 연결을 확인해주세요.")
    if st.button("연결 대기 화면으로 돌아가기"):
        disconnect_sensor()

