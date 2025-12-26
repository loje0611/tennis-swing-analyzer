# Tennis Logger systemd 서비스 설정 가이드

## 📋 개요

이 가이드는 Tennis Logger 애플리케이션을 systemd 서비스로 등록하여 부팅 시 자동으로 실행되도록 설정하는 방법을 설명합니다.

## 🚀 설치 방법

### 1. 서비스 설치

```bash
sudo ./install_service.sh
```

또는 수동으로:

```bash
# 서비스 파일 복사
sudo cp tennis-logger.service /etc/systemd/system/

# systemd 재로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅 시 자동 시작)
sudo systemctl enable tennis-logger.service

# 서비스 시작
sudo systemctl start tennis-logger.service
```

### 2. 서비스 상태 확인

```bash
sudo systemctl status tennis-logger
```

## 🔧 서비스 관리 명령

### 시작
```bash
sudo systemctl start tennis-logger
```

### 중지
```bash
sudo systemctl stop tennis-logger
```

### 재시작
```bash
sudo systemctl restart tennis-logger
```

### 상태 확인
```bash
sudo systemctl status tennis-logger
```

### 로그 확인
```bash
# 실시간 로그 보기
sudo journalctl -u tennis-logger -f

# 최근 로그 보기
sudo journalctl -u tennis-logger -n 50

# 오늘 로그 보기
sudo journalctl -u tennis-logger --since today
```

## ⚙️ 서비스 설정

서비스 파일 위치: `/etc/systemd/system/tennis-logger.service`

### 주요 설정

- **포트**: 8501 (변경하려면 서비스 파일의 `--server.port` 옵션 수정)
- **주소**: 0.0.0.0 (모든 네트워크 인터페이스에서 접근 가능)
- **자동 재시작**: 활성화됨 (오류 발생 시 10초 후 자동 재시작)
- **사용자**: keunu

### 포트 변경 방법

1. 서비스 파일 편집:
```bash
sudo nano /etc/systemd/system/tennis-logger.service
```

2. `--server.port=8501` 부분을 원하는 포트로 변경

3. systemd 재로드 및 서비스 재시작:
```bash
sudo systemctl daemon-reload
sudo systemctl restart tennis-logger
```

## 🗑️ 서비스 제거

```bash
# 서비스 중지 및 비활성화
sudo systemctl stop tennis-logger
sudo systemctl disable tennis-logger

# 서비스 파일 삭제
sudo rm /etc/systemd/system/tennis-logger.service

# systemd 재로드
sudo systemctl daemon-reload
```

## 🔍 문제 해결

### 서비스가 시작되지 않는 경우

1. **로그 확인**:
```bash
sudo journalctl -u tennis-logger -n 100
```

2. **가상 환경 확인**:
```bash
ls -la /home/keunu/tennis-swing-analyzer/venv/bin/streamlit
```

3. **파일 권한 확인**:
```bash
ls -la /home/keunu/tennis-swing-analyzer/tennis_logger.py
```

### 블루투스 관련 문제

서비스는 블루투스 서비스가 시작된 후에 실행됩니다. 블루투스가 비활성화되어 있으면 서비스 시작이 지연될 수 있습니다.

블루투스 상태 확인:
```bash
sudo systemctl status bluetooth
```

### 포트가 이미 사용 중인 경우

다른 애플리케이션이 8501 포트를 사용 중일 수 있습니다. 포트 확인:

```bash
sudo netstat -tulpn | grep 8501
```

또는:

```bash
sudo lsof -i :8501
```

## 📝 참고사항

- 서비스는 `keunu` 사용자로 실행됩니다
- 워킹 디렉토리는 `/home/keunu/tennis-swing-analyzer`입니다
- 로그는 systemd journal에 저장됩니다
- 애플리케이션은 헤드리스 모드로 실행됩니다 (브라우저 자동 열림 없음)

## 🌐 접속 방법

서비스가 실행되면 다음 주소로 접속할 수 있습니다:

- 로컬: `http://localhost:8501`
- 네트워크: `http://<라즈베리파이_IP>:8501`

IP 주소 확인:
```bash
hostname -I
```

