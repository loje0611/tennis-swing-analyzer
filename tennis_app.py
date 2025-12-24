import streamlit as st
import pandas as pd
import numpy as np
import time
import socket
from typing import Optional, Tuple
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 상수 정의 ---
SIMULATION_ITERATIONS = 100  # 시뮬레이션 반복 횟수
MAX_DATA_POINTS = 50  # 그래프에 표시할 최대 데이터 포인트 수
UPDATE_INTERVAL = 0.05  # 업데이트 간격 (초)
IMPACT_THRESHOLD = 10.0  # 임팩트 감지 임계값 (G)
SAMPLING_RATE = 0.1  # 샘플링 레이트

# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="Tennis Analyst Pro",
    page_icon="🎾",
    layout="wide"
)

# --- 2. IP 주소 가져오기 (아이패드 접속용) ---
def get_ip_address() -> str:
    """
    로컬 네트워크 IP 주소를 가져옵니다.
    
    Returns:
        str: IP 주소 또는 "localhost" (실패 시)
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except (socket.error, OSError) as e:
        logger.warning(f"IP 주소를 가져오는 중 오류 발생: {e}")
        return "localhost"

# --- 3. 세션 상태 초기화 ---
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'chart_data' not in st.session_state:
    st.session_state.chart_data = pd.DataFrame(columns=["Accel_X", "Accel_Y", "Accel_Z"])

# --- 4. 사이드바 (설정 및 정보) ---
with st.sidebar:
    st.title("⚙️ 설정")
    my_ip = get_ip_address()
    st.info(f"**접속 주소:**\nhttp://{my_ip}:8501")
    
    st.divider()
    
    mode = st.radio("데이터 소스", ["Simulation (가상)", "Real Sensor (ESP32)"])
    
    # ESP32 설정 (실제 센서 모드일 때)
    if mode == "Real Sensor (ESP32)":
        st.session_state.esp32_port = st.text_input(
            "시리얼 포트", 
            value="/dev/ttyUSB0", 
            help="ESP32가 연결된 시리얼 포트를 입력하세요", 
            key="esp32_port"
        )
        st.session_state.esp32_baudrate = st.number_input(
            "보드레이트", 
            min_value=9600, 
            max_value=115200, 
            value=115200, 
            step=9600, 
            key="esp32_baudrate"
        )
    
    st.divider()
    
    # 데이터 초기화 버튼
    if st.button("데이터 초기화", type="secondary"):
        st.session_state.chart_data = pd.DataFrame(columns=["Accel_X", "Accel_Y", "Accel_Z"])
        st.session_state.is_running = False
        st.rerun()
    
    st.write("---")
    st.caption("Developed by Brainstorming Partner")

# --- 5. 메인 화면 구성 ---
st.title("🎾 Tennis Swing Analyzer")
st.markdown("#### 실시간 스윙 데이터 모니터링")

# 상단 지표 (Metrics)
col1, col2, col3 = st.columns(3)
with col1:
    metric_speed = st.empty()
    metric_speed.metric("스윙 스피드", "0 km/h")
with col2:
    metric_force = st.empty()
    metric_force.metric("임팩트 강도", "0 G")
with col3:
    metric_spin = st.empty()
    metric_spin.metric("스핀량 (RPM)", "0")

st.divider()

# 그래프 영역
chart_placeholder = st.empty()

# --- 6. 데이터 처리 함수들 ---
def calculate_metrics(accel_x: float, accel_y: float, accel_z: float) -> Tuple[float, float, float]:
    """
    가속도 데이터로부터 지표를 계산합니다.
    
    Args:
        accel_x: X축 가속도
        accel_y: Y축 가속도
        accel_z: Z축 가속도
    
    Returns:
        Tuple[float, float, float]: (스피드 km/h, 임팩트 강도 G, 스핀량 RPM)
    """
    # 합성 가속도 (G 단위)
    force = np.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
    
    # 스피드 계산 (간단한 근사값)
    speed = force * 3.6  # km/h로 변환 (실제로는 더 복잡한 계산 필요)
    
    # 스핀량 계산 (Z축 가속도 기반)
    spin = abs(accel_z) * 100  # RPM 근사값
    
    return speed, force, spin

def generate_simulation_data(iteration: int) -> Tuple[float, float, float]:
    """
    시뮬레이션용 가속도 데이터를 생성합니다.
    
    Args:
        iteration: 현재 반복 횟수
    
    Returns:
        Tuple[float, float, float]: (Accel_X, Accel_Y, Accel_Z)
    """
    t = iteration * SAMPLING_RATE
    accel_x = 5 * np.sin(t) + np.random.normal(0, 0.5)
    accel_y = 10 * np.cos(t) + np.random.normal(0, 0.5)
    accel_z = 2 * np.sin(t * 2) + np.random.normal(0, 0.2)
    return accel_x, accel_y, accel_z

def update_chart_data(accel_x: float, accel_y: float, accel_z: float) -> pd.DataFrame:
    """
    차트 데이터를 업데이트합니다.
    
    Args:
        accel_x: X축 가속도
        accel_y: Y축 가속도
        accel_z: Z축 가속도
    
    Returns:
        pd.DataFrame: 업데이트된 차트 데이터
    """
    new_row = pd.DataFrame({
        "Accel_X": [accel_x],
        "Accel_Y": [accel_y],
        "Accel_Z": [accel_z]
    })
    
    # 기존 데이터에 추가
    updated_data = pd.concat([st.session_state.chart_data, new_row], ignore_index=True)
    
    # 최대 포인트 수 제한
    if len(updated_data) > MAX_DATA_POINTS:
        updated_data = updated_data.iloc[-MAX_DATA_POINTS:].reset_index(drop=True)
    
    return updated_data

# --- 7. ESP32 센서 연결 함수 ---
def connect_esp32(port: str, baudrate: int) -> Optional[object]:
    """
    ESP32 센서에 연결합니다.
    
    Args:
        port: 시리얼 포트 경로
        baudrate: 보드레이트
    
    Returns:
        시리얼 연결 객체 또는 None
    """
    try:
        import serial
        ser = serial.Serial(port, baudrate, timeout=1)
        logger.info(f"ESP32 연결 성공: {port} @ {baudrate}")
        return ser
    except ImportError:
        logger.error("pyserial 라이브러리가 설치되지 않았습니다. 'pip install pyserial'을 실행하세요.")
        return None
    except (serial.SerialException, OSError) as e:
        logger.error(f"ESP32 연결 실패: {e}")
        return None

def read_esp32_data(ser: object) -> Optional[Tuple[float, float, float]]:
    """
    ESP32로부터 데이터를 읽습니다.
    
    Args:
        ser: 시리얼 연결 객체
    
    Returns:
        Tuple[float, float, float] 또는 None: (Accel_X, Accel_Y, Accel_Z)
    """
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            # CSV 형식: "x,y,z" 또는 JSON 형식 등으로 파싱
            parts = line.split(',')
            if len(parts) == 3:
                return float(parts[0]), float(parts[1]), float(parts[2])
    except (ValueError, AttributeError, UnicodeDecodeError) as e:
        logger.warning(f"ESP32 데이터 읽기 오류: {e}")
    return None

# --- 8. 데이터 시뮬레이션 로직 ---
def run_simulation():
    """시뮬레이션 모드를 실행합니다."""
    start_btn = st.button("분석 시작 (Start)", type="primary", disabled=st.session_state.is_running)
    
    if start_btn and not st.session_state.is_running:
        st.session_state.is_running = True
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        try:
            for i in range(SIMULATION_ITERATIONS):
                if not st.session_state.is_running:
                    break
                
                # 데이터 생성
                accel_x, accel_y, accel_z = generate_simulation_data(i)
                
                # 차트 데이터 업데이트
                st.session_state.chart_data = update_chart_data(accel_x, accel_y, accel_z)
                
                # 지표 계산
                speed, force, spin = calculate_metrics(accel_x, accel_y, accel_z)
                
                # 화면 업데이트
                if not st.session_state.chart_data.empty:
                    chart_placeholder.line_chart(st.session_state.chart_data)
                
                metric_speed.metric("스윙 스피드", f"{speed:.2f} km/h")
                metric_force.metric("임팩트 강도", f"{force:.2f} G")
                metric_spin.metric("스핀량 (RPM)", f"{spin:.0f}")
                
                # 임팩트 감지
                if force > IMPACT_THRESHOLD:
                    progress_text.warning("💥 임팩트 감지!")
                else:
                    progress_text.text("스윙 대기 중...")
                
                # 진행률 업데이트
                progress_bar.progress((i + 1) / SIMULATION_ITERATIONS)
                
                time.sleep(UPDATE_INTERVAL)
            
            st.success("분석 종료!")
            progress_bar.empty()
            
        except Exception as e:
            logger.error(f"시뮬레이션 중 오류 발생: {e}")
            st.error(f"오류가 발생했습니다: {e}")
        finally:
            st.session_state.is_running = False

# --- 9. 실제 센서 모드 실행 ---
def run_real_sensor(port: str, baudrate: int):
    """실제 ESP32 센서 모드를 실행합니다."""
    ser = connect_esp32(port, baudrate)
    
    if ser is None:
        st.error("⚠️ ESP32 센서 연결에 실패했습니다. 시리얼 포트와 보드레이트를 확인하세요.")
        st.info("💡 시뮬레이션 모드를 사용하거나 'pip install pyserial'을 실행하세요.")
        return
    
    start_btn = st.button("분석 시작 (Start)", type="primary", disabled=st.session_state.is_running)
    
    if start_btn and not st.session_state.is_running:
        st.session_state.is_running = True
        progress_text = st.empty()
        
        try:
            while st.session_state.is_running:
                data = read_esp32_data(ser)
                
                if data is not None:
                    accel_x, accel_y, accel_z = data
                    
                    # 차트 데이터 업데이트
                    st.session_state.chart_data = update_chart_data(accel_x, accel_y, accel_z)
                    
                    # 지표 계산
                    speed, force, spin = calculate_metrics(accel_x, accel_y, accel_z)
                    
                    # 화면 업데이트
                    if not st.session_state.chart_data.empty:
                        chart_placeholder.line_chart(st.session_state.chart_data)
                    
                    metric_speed.metric("스윙 스피드", f"{speed:.2f} km/h")
                    metric_force.metric("임팩트 강도", f"{force:.2f} G")
                    metric_spin.metric("스핀량 (RPM)", f"{spin:.0f}")
                    
                    # 임팩트 감지
                    if force > IMPACT_THRESHOLD:
                        progress_text.warning("💥 임팩트 감지!")
                    else:
                        progress_text.text("데이터 수신 중...")
                
                time.sleep(UPDATE_INTERVAL)
        
        except KeyboardInterrupt:
            st.info("사용자에 의해 중단되었습니다.")
        except Exception as e:
            logger.error(f"센서 읽기 중 오류 발생: {e}")
            st.error(f"오류가 발생했습니다: {e}")
        finally:
            if ser:
                ser.close()
            st.session_state.is_running = False

# --- 10. 실행 ---
if mode == "Simulation (가상)":
    run_simulation()
else:
    # 사이드바에서 정의한 ESP32 설정 사용
    port = st.session_state.get('esp32_port', '/dev/ttyUSB0')
    baudrate = st.session_state.get('esp32_baudrate', 115200)
    run_real_sensor(port, baudrate)

