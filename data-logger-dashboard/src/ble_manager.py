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

    async def scan(self) -> Tuple[bool, str, Optional[object]]:
        try:
            logger.info("BLE 스캔 시작 (Timeout: 5.0s)...")
            # discover returns a tuple of (device, advertisement_data) dict in newer Bleak versions if return_adv=True is used, 
            # BUT standard discover returns a list of BLEDevice objects which DO NOT have metadata directly.
            # We need to use scanning with callback or just check the device object properties carefully.
            
            # Actually, standard discover() returns List[BLEDevice]. 
            # BLEDevice has .metadata only in some versions or it's on the advertisement data.
            # Let's use discover(return_adv=True) to get both.
            
            devices_dict = await BleakScanner.discover(timeout=5.0, return_adv=True)
            
            target_device = None
            found_log = []
            
            for address, (device, advertisement_data) in devices_dict.items():
                name = device.name or "Unknown"
                uuids = advertisement_data.service_uuids
                rssi = advertisement_data.rssi
                found_log.append(f"- {name} [{device.address}] (RSSI: {rssi}, UUIDs: {uuids})")
                
                # 1. Check Service UUID
                if SERVICE_UUID.lower() in [str(u).lower() for u in uuids]:
                    target_device = device
                    logger.info(f"UUID로 디바이스 찾음: {name}")
                    break
                
                # 2. Check Device Name (Fallback)
                if name == TARGET_DEVICE_NAME:
                    target_device = device
                    logger.info(f"이름으로 디바이스 찾음: {name}")
                    break
            
            if not target_device:
                logger.warning("스캔 결과:\n" + "\n".join(found_log))
                
                # Sort found_log by RSSI (descending) if possible, but they are strings now.
                # Let's recreate a simple list for display
                sorted_devices = sorted(devices_dict.values(), key=lambda x: x[1].rssi, reverse=True)
                top_devices = []
                for idx, (dev, adv) in enumerate(sorted_devices[:10]):
                    name = dev.name or "Unknown"
                    top_devices.append(f"{idx+1}. {name} ({adv.rssi}dBm) [{dev.address}]")
                
                device_list_str = "\n".join(top_devices)
                
                # Create a more detailed debug string with UUIDs
                debug_details = []
                for idx, (dev, adv) in enumerate(sorted_devices[:5]): # Top 5 details
                     debug_details.append(f"{idx+1}. {dev.name} [{dev.address}]")
                     debug_details.append(f"   RSSI: {adv.rssi}")
                     debug_details.append(f"   UUIDs: {adv.service_uuids}")
                
                debug_str = "\n".join(debug_details)
                
                return False, f"디바이스를 찾을 수 없습니다.\n\n[상위 5개 디바이스 상세]\n{debug_str}", None
            
            return True, f"디바이스 발견: {target_device.name or target_device.address}", target_device
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
                    
                    if decoded == "ERR:NO_SENSOR":
                         self.sensor_status = "error"
                         return

                    parts = decoded.split(',')
                    if len(parts) == 6:
                        # Sensor is OK
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
            self.last_error = str(e)
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


