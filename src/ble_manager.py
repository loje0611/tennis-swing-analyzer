import abc
import asyncio
import threading
import logging
from datetime import datetime
from queue import Queue
from typing import Optional, Tuple, List
from bleak import BleakScanner, BleakClient
from src.config import TARGET_DEVICE_NAME, SERVICE_UUID, CHARACTERISTIC_UUID

logger = logging.getLogger(__name__)

class BLEManager(abc.ABC):
    def __init__(self, data_queue: Queue):
        self.data_queue = data_queue
        self.connected = False
        self.running = False

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

    async def scan(self) -> Tuple[bool, str, Optional[object]]:
        try:
            devices = await BleakScanner.discover(timeout=5.0)
            target_device = None
            for device in devices:
                if device.name == TARGET_DEVICE_NAME:
                    target_device = device
                    break
            
            if target_device is None:
                return False, f"{TARGET_DEVICE_NAME} 디바이스를 찾을 수 없습니다.", None
            
            return True, "디바이스 발견", target_device
        except Exception as e:
            logger.error(f"스캔 오류: {e}")
            return False, f"오류: {str(e)}", None

    def start_connection(self, address: str):
        if self.running:
            return
        
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
            self.client = BleakClient(address)
            await self.client.connect()
            logger.info(f"BLE 연결 성공: {address}")
            self.connected = True
            
            def notification_handler(sender, data: bytearray):
                try:
                    decoded = data.decode('utf-8').strip()
                    parts = decoded.split(',')
                    if len(parts) == 6:
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
                        except:
                            try:
                                self.data_queue.get_nowait()
                                self.data_queue.put_nowait(data_point)
                                self.queue_overflow_count += 1
                            except:
                                pass
                except Exception as e:
                    logger.warning(f"데이터 파싱 오류: {e}")
            
            await self.client.start_notify(CHARACTERISTIC_UUID, notification_handler)
            logger.info("Notification 시작됨")
            
            while self.running and self.client.is_connected:
                await asyncio.sleep(0.1)
            
            if self.client.is_connected:
                await self.client.stop_notify(CHARACTERISTIC_UUID)
                await self.client.disconnect()
            
        except Exception as e:
            logger.error(f"BLE 연결/수집 오류: {e}")
        finally:
            self.connected = False
            if self.client and self.client.is_connected:
                try:
                    await self.client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass
                try:
                    await self.client.disconnect()
                except Exception:
                    pass

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.connected = False


