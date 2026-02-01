#!/bin/bash
# Data Logger Dashboard 실행 스크립트

cd "$(dirname "$0")"
./venv/bin/python3 -m streamlit run data_logger_dashboard.py

