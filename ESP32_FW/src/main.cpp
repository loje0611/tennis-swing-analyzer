#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Wire.h>
#include <esp_bt.h>

// --- BLE Configuration ---
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define DEVICE_NAME         "Tennis_Sensor_V1"

// MPU6050
#define MPU6050_ADDR    0x68
#define REG_PWR_MGMT_1  0x6B
#define REG_GYRO_CONFIG  0x1B   // 0x18 = ±2000 dps
#define REG_ACCEL_CONFIG 0x1C   // 0x18 = ±16g
#define REG_ACCEL_XOUT_H 0x3B

// Scale factors for ±2000 dps gyro, ±16g accel (set in Init)
#define GYRO_SCALE  16.4f   // LSB per deg/s
#define ACCEL_SCALE 2048.0f // LSB per g

// I2C Pins (Seeed XIAO ESP32C3)
#define SDA_PIN D4
#define SCL_PIN D5

// Sampling: 50 Hz
const unsigned long SAMPLING_INTERVAL_MS = 20;
unsigned long last_sample_time = 0;

// BLE
NimBLEServer* pServer = NULL;
NimBLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

// --- MPU6050 ---
bool MPU6050_Init() {
  if (!Wire.begin(SDA_PIN, SCL_PIN)) {
    Serial.println("I2C Init Failed");
    return false;
  }
  Wire.setClock(400000); // Fast Mode 400 kHz

  // Wake up MPU6050
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(REG_PWR_MGMT_1);
  Wire.write(0);
  if (Wire.endTransmission(true) != 0) {
    Serial.println("MPU6050 Wakeup Failed");
    return false;
  }

  // Gyro: ±2000 dps (0x18 → FS_SEL=3)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(REG_GYRO_CONFIG);
  Wire.write(0x18);
  if (Wire.endTransmission(true) != 0) {
    Serial.println("MPU6050 Gyro Config Failed");
    return false;
  }

  // Accel: ±16g (0x18 → AFS_SEL=3)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(REG_ACCEL_CONFIG);
  Wire.write(0x18);
  if (Wire.endTransmission(true) != 0) {
    Serial.println("MPU6050 Accel Config Failed");
    return false;
  }

  return true;
}

bool MPU6050_Read(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(REG_ACCEL_XOUT_H);
  if (Wire.endTransmission(false) != 0) return false;

  if (Wire.requestFrom((uint8_t)MPU6050_ADDR, (size_t)14, (bool)true) != 14)
    return false;

  int16_t raw_ax = Wire.read() << 8 | Wire.read();
  int16_t raw_ay = Wire.read() << 8 | Wire.read();
  int16_t raw_az = Wire.read() << 8 | Wire.read();
  (void)(Wire.read() << 8 | Wire.read()); // temperature
  int16_t raw_gx = Wire.read() << 8 | Wire.read();
  int16_t raw_gy = Wire.read() << 8 | Wire.read();
  int16_t raw_gz = Wire.read() << 8 | Wire.read();

  ax = raw_ax / ACCEL_SCALE;
  ay = raw_ay / ACCEL_SCALE;
  az = raw_az / ACCEL_SCALE;
  gx = raw_gx / GYRO_SCALE;
  gy = raw_gy / GYRO_SCALE;
  gz = raw_gz / GYRO_SCALE;
  return true;
}

// --- BLE Callbacks ---
// Base class has only onConnect(NimBLEServer*); get conn handle via getPeerInfo(0) after connect.
class MyServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* pServer) override {
    deviceConnected = true;
    Serial.println("Client connected");
    // Supervision timeout 100*10ms = 1s: drop connection if peer (e.g. Pi) does not respond
    if (pServer->getConnectedCount() > 0) {
      NimBLEConnInfo peer = pServer->getPeerInfo((uint8_t)0);
      pServer->updateConnParams(peer.getConnHandle(), 24, 40, 0, 100);
    }
  }
  void onDisconnect(NimBLEServer* pServer) override {
    (void)pServer;
    deviceConnected = false;
    Serial.println("Client disconnected");
    NimBLEDevice::startAdvertising();
  }
};

void setup() {
  Serial.begin(115200);

  if (!MPU6050_Init()) {
    Serial.println("MPU6050 Init Failed");
  } else {
    Serial.println("MPU6050 OK (Gyro ±2000dps, Accel ±16g)");
  }

  NimBLEDevice::init(DEVICE_NAME);
  NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  Serial.print("MAC: ");
  Serial.println(NimBLEDevice::getAddress().toString().c_str());

  pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  NimBLEService* pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
      CHARACTERISTIC_UUID,
      NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  pService->start();

  NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
  NimBLEAdvertisementData advData;
  advData.setFlags(0x06);
  advData.setCompleteServices(NimBLEUUID(SERVICE_UUID));
  NimBLEAdvertisementData scanData;
  scanData.setName(DEVICE_NAME);
  pAdvertising->setAdvertisementData(advData);
  pAdvertising->setScanResponseData(scanData);
  pAdvertising->start();

  Serial.println("BLE advertising started");
}

void loop() {
  unsigned long now = millis();

  if (deviceConnected && (now - last_sample_time >= SAMPLING_INTERVAL_MS)) {
    last_sample_time = now;
    float ax, ay, az, gx, gy, gz;

    if (MPU6050_Read(ax, ay, az, gx, gy, gz)) {
      char buf[64];
      int n = snprintf(buf, sizeof(buf), "%.3f,%.3f,%.3f,%.3f,%.3f,%.3f", ax, ay, az, gx, gy, gz);
      if (n > 0) {
        pCharacteristic->setValue((uint8_t*)buf, (size_t)n);
        pCharacteristic->notify();
      }
    } else {
      const char* err = "ERR:NO_SENSOR";
      pCharacteristic->setValue((uint8_t*)err, strlen(err));
      pCharacteristic->notify();
      static unsigned long last_retry = 0;
      if (now - last_retry > 1000) {
        last_retry = now;
        MPU6050_Init();
      }
    }
  }

  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    pServer->getAdvertising()->start();
    Serial.println("Advertising restarted");
  }
  oldDeviceConnected = deviceConnected;
}
