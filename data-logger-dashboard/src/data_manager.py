import os
import csv
import re
from datetime import datetime
from typing import List, Dict
from src.config import DATA_FOLDER

# 파일명 패턴: YYYYMMDD_HHMMSS_{Main}_{Sub}.csv
LABEL_FILENAME_PATTERN = re.compile(r"^\d{8}_\d{6}_(.+)_(.+)\.csv$")


def get_label_file_counts() -> Dict[str, int]:
    """데이터 폴더를 스캔하여 라벨(카테고리_타입)별 저장된 CSV 파일 개수를 반환."""
    counts = {}
    for main in ("Forehand", "Backhand"):
        for sub in ("Flat", "Topspin", "Slice"):
            counts[f"{main}_{sub}"] = 0
    if not os.path.isdir(DATA_FOLDER):
        return counts
    for name in os.listdir(DATA_FOLDER):
        if not name.endswith(".csv"):
            continue
        m = LABEL_FILENAME_PATTERN.match(name)
        if m:
            label = f"{m.group(1)}_{m.group(2)}"
            counts[label] = counts.get(label, 0) + 1
    return counts


def save_data_to_csv(data: List[Dict], main_category: str, sub_category: str) -> str:
    """데이터를 CSV 파일로 저장"""
    # data 폴더 생성
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    # 파일명 생성: YYYYMMDD_HHMMSS_{Main}_{Sub}.csv
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{main_category}_{sub_category}.csv"
    filepath = os.path.join(DATA_FOLDER, filename)
    
    # CSV 파일 작성
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['timestamp', 'ax', 'ay', 'az', 'gx', 'gy', 'gz']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in data:
            writer.writerow({
                'timestamp': row.get('timestamp_ms', 0),
                'ax': row['accel_x'],
                'ay': row['accel_y'],
                'az': row['accel_z'],
                'gx': row['gyro_x'],
                'gy': row['gyro_y'],
                'gz': row['gyro_z']
            })
    
    return filepath
