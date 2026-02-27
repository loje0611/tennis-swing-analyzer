import os

# --- 상수 정의 ---
TARGET_DEVICE_NAME = os.getenv("TARGET_DEVICE_NAME", "Tennis_Sensor_V1")
TARGET_DEVICE_ADDRESS = os.getenv("TARGET_DEVICE_ADDRESS", "94:A9:90:6A:CC:E2") # Known Sensor MAC
SERVICE_UUID = os.getenv("SERVICE_UUID", "4fafc201-1fb5-459e-8fcc-c5c9c331914b")
CHARACTERISTIC_UUID = os.getenv("CHARACTERISTIC_UUID", "beb5483e-36e1-4688-b7f5-ea07361b26a8")

DATA_FOLDER = os.getenv("DATA_FOLDER", os.path.join(os.path.dirname(__file__), "..", "data"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", 10000))  # 큐 최대 크기 (약 100Hz 샘플링 시 100초분)

# --- 추론 관련 상수 ---
PEAK_ACCEL_THRESHOLD_G = 1.5       # 스윙 피크 감지 가속도 임계값 (G)
PEAK_COOLDOWN_SEC = 1.5            # 피크 감지 쿨다운 (초)
PACING_DELAY_SEC = 2.0             # 페이싱 가이드 딜레이 (초)
INFERENCE_PEAK_THRESHOLD_G = 2.5   # 추론 트리거 가속도 임계값 (G)
INFERENCE_FALSE_POSITIVE_G = 3.0   # 오탐 방지 최소 가속도 (G)
INFERENCE_WINDOW_SAMPLES = 50      # 추론 윈도우 크기 (샘플 수)
INFERENCE_BUFFER_SIZE = 150        # 추론 버퍼 크기 (샘플 수, 약 3초)
INFERENCE_FUTURE_SAMPLES = 30      # 피크 이후 대기 샘플 수
INFERENCE_COOLDOWN_FRAMES = 50     # 추론 쿨다운 프레임 수 (50Hz 기준 1초)
SWING_CONFIDENCE_THRESHOLD = 0.60  # 스윙 분류 최소 신뢰도

# --- 속도 계산 상수 ---
RACKET_RADIUS_M = 1.1              # 팔 + 라켓 유효 반경 (m)
SPEED_CALIBRATION_FACTOR = 1.2     # 속도 보정 계수
SPEED_HISTORY_WINDOW_SEC = 2.0     # 속도 히스토리 윈도우 (초)
