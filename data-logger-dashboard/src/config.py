import os

# --- 상수 정의 ---
TARGET_DEVICE_NAME = os.getenv("TARGET_DEVICE_NAME", "Tennis_Sensor_V1")
TARGET_DEVICE_ADDRESS = os.getenv("TARGET_DEVICE_ADDRESS", "94:A9:90:6A:CC:E2") # Known Sensor MAC
SERVICE_UUID = os.getenv("SERVICE_UUID", "4fafc201-1fb5-459e-8fcc-c5c9c331914b")
CHARACTERISTIC_UUID = os.getenv("CHARACTERISTIC_UUID", "beb5483e-36e1-4688-b7f5-ea07361b26a8")

DATA_FOLDER = os.getenv("DATA_FOLDER", os.path.join(os.path.dirname(__file__), "..", "data"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", 10000))  # 큐 최대 크기 (약 100Hz 샘플링 시 100초분)

# --- 추론 관련 상수 (50Hz, 1.2s 비대칭 윈도우) ---
PEAK_ACCEL_THRESHOLD_G = 1.5       # 스윙 피크 감지 가속도 임계값 (G)
PEAK_COOLDOWN_SEC = 1.5            # 피크 감지 쿨다운 (초)
PACING_DELAY_SEC = 2.0             # 페이싱 가이드 딜레이 (초)
INFERENCE_PEAK_THRESHOLD_G = 2.5   # (레거시) 피크 감지용
INFERENCE_TRIGGER_THRESHOLD_G = 3.0  # True Peak 정렬: 이 값을 넘으면 State 2 전환 (40샘플 대기)
INFERENCE_FALSE_POSITIVE_G = 3.0   # 오탐 방지 최소 가속도 (G)
# 1.2초 비대칭: [TruePeak-20 : TruePeak+40] = 60샘플 (피크를 인덱스 20에 정렬)
INFERENCE_WINDOW_SAMPLES = 60     # 추론 윈도우 크기 (샘플 수)
INFERENCE_PEAK_PAST_SAMPLES = 20  # 피크 이전 샘플 수 (400ms)
INFERENCE_FUTURE_SAMPLES = 40     # 트리거 후 대기 샘플 수 (800ms) 후 True Peak 검색
INFERENCE_BUFFER_SIZE = 150       # 넉넉한 버퍼 (과거 데이터 보존)
INFERENCE_PEAK_SEARCH_WINDOW = 100  # True Peak 검색 시 최근 N샘플 내에서 argmax
INFERENCE_COOLDOWN_FRAMES = 50    # 추론 쿨다운 프레임 수 (50Hz 기준 1초)
SWING_CONFIDENCE_THRESHOLD = 0.60  # 스윙 분류 최소 신뢰도

# --- 속도 계산 상수 ---
RACKET_RADIUS_M = 1.1              # 팔 + 라켓 유효 반경 (m)
SPEED_CALIBRATION_FACTOR = 1.2     # 속도 보정 계수
SPEED_HISTORY_WINDOW_SEC = 2.0     # 속도 히스토리 윈도우 (초)
