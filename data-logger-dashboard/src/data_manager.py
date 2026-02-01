import os
import csv
from datetime import datetime
from typing import List, Dict
from src.config import DATA_FOLDER

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
