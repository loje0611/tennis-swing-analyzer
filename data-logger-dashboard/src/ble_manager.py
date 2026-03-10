import abc
import asyncio
import threading
import logging
from datetime import datetime
from queue import Queue
from typing import Optional, Tuple
from bleak import BleakScanner, BleakClient
from src.config import TARGET_DEVICE_NAME, SERVICE_UUID, CHARACTERISTIC_UUID

logger = logging.getLogger(__name__)

class BLEManager(abc.ABC):
    def __init__(self, data_queue: Queue):
        self.data_queue = data_queue
        self.connected = False
        self.running = False
        self.sensor_status = "unknown" # unknown, ok, error

    @abc.abstractmethod
    def start_connection(self, address: str):
        pass

    @abc.abstractmethod
    def stop(self):
        pass
        
    @abc.abstractmethod
    async def scan(self) -> Tuple[bool, str, Optional[object]]:
        """
        Returns: (success, message, device_object)
        """
        pass

class RealBLEManager(BLEManager):
    def __init__(self, data_queue: Queue):
        super().__init__(data_queue)
        self.client: Optional[BleakClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.queue_overflow_count = 0
        self.last_error = None
        self._disconnect_event = threading.Event()

    async def scan(self) -> Tuple[bool, str, Optional[object]]:
        try:
            logger.info("BLE 스캔 시작 (Timeout: 5.0s)...")
            
            # 1. UUID 필터 없이 모든 장치 스캔
            devices_dict = await BleakScanner.discover(timeout=5.0, return_adv=True)
            
            target_device = None
            found_log = []
            
            # 3. 디버깅 강화: 모든 장치 로그 출력
            logger.info(f"스캔된 장치 수: {len(devices_dict)}")
            
            from src.config import TARGET_DEVICE_ADDRESS
            
            for address, (device, advertisement_data) in devices_dict.items():
                name = device.name or "Unknown"
                uuids = advertisement_data.service_uuids
                rssi = advertisement_data.rssi
                
                log_entry = f"- {name} [{device.address}] (RSSI: {rssi}, UUIDs: {uuids})"
                found_log.append(log_entry)
                print(f"DEBUG_SCAN: {log_entry}") # Console Output

                # 2. 필터링 로직 (이름 기반 Priority)
                # 조건 1: 이름이 "Tennis_Sensor_V1"와 일치
                if name == "Tennis_Sensor_V1":
                    target_device = device
                    logger.info(f"🎯 이름으로 디바이스 찾음: {name}")
                    break
                
                # 조건 2: UUID 확인 (Secondary)
                if SERVICE_UUID.lower() in [str(u).lower() for u in uuids]:
                    target_device = device
                    logger.info(f"🎯 UUID로 디바이스 찾음: {name}")
                    break
                    
                # 조건 3: MAC 주소 (Last Resort)
                if device.address == TARGET_DEVICE_ADDRESS:
                    target_device = device
                    logger.info(f"🎯 MAC 주소로 디바이스 찾음: {name}")
                    break
            
            if not target_device:
                logger.warning("스캔 결과 (상세):\n" + "\n".join(found_log))
                return False, f"디바이스 'Tennis_Sensor_V1'를 찾을 수 없습니다.\n(스캔된 장치: {len(devices_dict)}개)", None
            
            return True, f"디바이스 발견: {target_device.name} [{target_device.address}]", target_device
            
        except Exception as e:
            logger.error(f"스캔 오류: {e}")
            return False, f"오류: {str(e)}", None

    def start_connection(self, address: str):
        if self.running:
            return
        self._disconnect_event.clear()
        self.running = True
        self.thread = threading.Thread(target=self._run_async_loop, args=(address,), daemon=True)
        self.thread.start()

    def _run_async_loop(self, address: str):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect_and_collect(address))
        except Exception as e:
            logger.error(f"BLE 루프 오류: {e}")
        finally:
            self.loop.close()
            self.running = False
            self.connected = False

    async def _connect_and_collect(self, address: str):
        try:
            if self.client and self.client.is_connected:
                logger.info("기존 연결 해제 중...")
                await self.client.disconnect()

            self.client = BleakClient(address)
            await self.client.connect()
            logger.info(f"BLE 연결 성공: {address}")
            self.connected = True

            logger.info("--- 서비스 목록 ---")
            for service in self.client.services:
                logger.info(f"Service: {service.uuid} ({service.description})")
                for char in service.characteristics:
                    logger.info(f"  - Char: {char.uuid} ({char.properties})")
            logger.info("-------------------")

            def notification_handler(sender, data: bytearray):
                try:
                    decoded = data.decode('utf-8').strip()
                    if decoded == "ERR:NO_SENSOR":
                        self.sensor_status = "error"
                        return
                    parts = decoded.split(',')
                    if len(parts) == 6:
                        self.sensor_status = "ok"
                        timestamp = datetime.now()
                        data_point = {
                            'timestamp': timestamp,
                            'accel_x': float(parts[0]),
                            'accel_y': float(parts[1]),
                            'accel_z': float(parts[2]),
                            'gyro_x': float(parts[3]),
                            'gyro_y': float(parts[4]),
                            'gyro_z': float(parts[5])
                        }
                        try:
                            self.data_queue.put_nowait(data_point)
                        except Exception:
                            try:
                                self.data_queue.get_nowait()
                                self.data_queue.put_nowait(data_point)
                                self.queue_overflow_count += 1
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning(f"데이터 파싱 오류: {e}")

            await self.client.start_notify(CHARACTERISTIC_UUID, notification_handler)
            logger.info("Notification 시작됨")

            # Graceful shutdown: break when _disconnect_event is set (e.g. atexit/stop)
            while self.running and self.client.is_connected and not self._disconnect_event.is_set():
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"BLE 연결/수집 오류: {e}")
            self.last_error = str(e)
        finally:
            self.connected = False
            # 확실한 cleanup: 항상 notify 해제(핸들러 정리) 후 disconnect로 BlueZ 캐시 정리
            if self.client:
                try:
                    await self.client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
                self.client = None

    def stop(self):
        self._disconnect_event.set()
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.connected = False


