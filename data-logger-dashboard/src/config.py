import os

# --- 상수 정의 ---
TARGET_DEVICE_NAME = os.getenv("TARGET_DEVICE_NAME", "Tennis_Sensor_V1")
TARGET_DEVICE_ADDRESS = os.getenv("TARGET_DEVICE_ADDRESS", "94:A9:90:6A:CC:E2") # Known Sensor MAC
SERVICE_UUID = os.getenv("SERVICE_UUID", "4fafc201-1fb5-459e-8fcc-c5c9c331914b")
CHARACTERISTIC_UUID = os.getenv("CHARACTERISTIC_UUID", "beb5483e-36e1-4688-b7f5-ea07361b26a8")

DATA_FOLDER = os.getenv("DATA_FOLDER", os.path.join(os.path.dirname(__file__), "..", "data"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", 10000))  # 큐 최대 크기 (약 100Hz 샘플링 시 100초분)
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "model.eim"))
