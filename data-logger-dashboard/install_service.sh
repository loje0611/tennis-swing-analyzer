#!/bin/bash
# Tennis Logger systemd 서비스 설치 스크립트

SERVICE_NAME="data-logger-dashboard"
SERVICE_FILE="data-logger-dashboard.service"
SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Data Logger Dashboard systemd 서비스 설치 ==="

# 서비스 파일이 있는지 확인
if [ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]; then
    echo "❌ 오류: $SERVICE_FILE 파일을 찾을 수 없습니다."
    exit 1
fi

# sudo 권한 확인
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  sudo 권한이 필요합니다."
    echo "다음 명령을 실행하세요:"
    echo "  sudo $0"
    exit 1
fi

# 서비스 파일 복사
echo "📋 서비스 파일 복사 중..."
cp "$SCRIPT_DIR/$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_FILE"
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

# systemd 재로드
echo "🔄 systemd 재로드 중..."
systemctl daemon-reload

# 서비스 활성화
echo "✅ 서비스 활성화 중..."
systemctl enable "$SERVICE_NAME.service"

echo ""
echo "✅ 설치 완료!"
echo ""
echo "서비스 관리 명령:"
echo "  시작:   sudo systemctl start $SERVICE_NAME"
echo "  중지:   sudo systemctl stop $SERVICE_NAME"
echo "  상태:   sudo systemctl status $SERVICE_NAME"
echo "  재시작: sudo systemctl restart $SERVICE_NAME"
echo "  로그:   sudo journalctl -u $SERVICE_NAME -f"
echo ""

