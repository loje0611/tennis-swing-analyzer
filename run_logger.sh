#!/bin/bash
# Tennis Logger V2 실행 스크립트

cd "$(dirname "$0")"
source venv/bin/activate
streamlit run tennis_logger_v2.py

