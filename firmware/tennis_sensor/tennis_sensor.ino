#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Wire.h>

// --- Configuration ---
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define DEVICE_NAME         "Tennis_Sensor_V1"

// MPU6050 I2C Address
#define MPU6050_ADDR 0x68

// LED Pin (Seeed XIAO ESP32C3)
// LED_BUILTIN is usually defined. 
// Logic: Active LOW (LOW = ON, HIGH = OFF)
#ifndef LED_BUILTIN
  #define LED_BUILTIN 8 
#endif

#define LED_ON  LOW
#define LED_OFF HIGH

// Sampling Rate
const unsigned long SAMPLING_INTERVAL_MS = 20; // 50Hz
unsigned long last_sample_time = 0;

// BLE Globals
NimBLEServer* pServer = NULL;
NimBLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

// --- MPU6050 Helper Functions ---

void MPU6050_Init() {
  Wire.begin();
  Wire.setClock(400000); // <--- 이 줄 추가 (I2C 속도를 400kHz로 증가)
  
  // Wake up MPU6050
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(0x6B);  // PWR_MGMT_1 register
  Wire.write(0);     // set to zero used to wake up the MPU-6050
  Wire.endTransmission(true);
}

void MPU6050_Read(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(0x3B);  // starting with register 0x3B (ACCEL_XOUT_H)
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)MPU6050_ADDR, (size_t)14, (bool)true);  // request a total of 14 registers

  int16_t raw_ax = Wire.read() << 8 | Wire.read();
  int16_t raw_ay = Wire.read() << 8 | Wire.read();
  int16_t raw_az = Wire.read() << 8 | Wire.read();
  int16_t raw_temp = Wire.read() << 8 | Wire.read(); // temperature, ignore
  int16_t raw_gx = Wire.read() << 8 | Wire.read();
  int16_t raw_gy = Wire.read() << 8 | Wire.read();
  int16_t raw_gz = Wire.read() << 8 | Wire.read();

  // Simple conversion (assuming default scales)
  // Accel: 16384 LSB/g
  // Gyro: 131 LSB/deg/s
  ax = raw_ax / 16384.0;
  ay = raw_ay / 16384.0;
  az = raw_az / 16384.0;
  
  gx = raw_gx / 131.0;
  gy = raw_gy / 131.0;
  gz = raw_gz / 131.0;
}

// --- BLE Callbacks ---
class MyServerCallbacks: public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer) {
      deviceConnected = true;
    };

    void onDisconnect(NimBLEServer* pServer) {
      deviceConnected = false;
    }
};

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LED_OFF); // Off initially

  // Init MPU6050
  MPU6050_Init();
  Serial.println("MPU6050 Initialized");

  // Init NimBLE
  NimBLEDevice::init(DEVICE_NAME);
  pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  NimBLEService *pService = pServer->createService(SERVICE_UUID);

  // NimBLE does not need manual BLE2902 descriptor
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      NIMBLE_PROPERTY::READ |
                      NIMBLE_PROPERTY::NOTIFY
                    );

  pService->start();

  // Start advertising
  NimBLEAdvertising *pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  
  // NimBLE specific advertising settings can be added here if needed
  // pAdvertising->setMinPreferred(0x06); 
  
  pAdvertising->start();
  Serial.println("Waiting for a client connection to notify...");
}

void loop() {
  unsigned long current_time = millis();

  // LED Logic: Blink if not connected, Solid ON if connected
  // Active Low: LOW is ON, HIGH is OFF
  if (!deviceConnected) {
    // Blink every 500ms
    if ((current_time / 500) % 2 == 0) {
      digitalWrite(LED_BUILTIN, LED_ON); 
    } else {
      digitalWrite(LED_BUILTIN, LED_OFF);
    }
  } else {
    digitalWrite(LED_BUILTIN, LED_ON); // Connected -> Solid ON
  }

  // Sampling Logic
  if (deviceConnected) {
    if (current_time - last_sample_time >= SAMPLING_INTERVAL_MS) {
      last_sample_time = current_time;

      float ax, ay, az, gx, gy, gz;
      MPU6050_Read(ax, ay, az, gx, gy, gz);

      // Create CSV string: "ax,ay,az,gx,gy,gz"
      char dataStr[64]; 
      snprintf(dataStr, sizeof(dataStr), "%.3f,%.3f,%.3f,%.3f,%.3f,%.3f", 
               ax, ay, az, gx, gy, gz);

      pCharacteristic->setValue(dataStr);
      pCharacteristic->notify();
    }
  }

  // NimBLE handles advertising restart automatically on disconnect usually, 
  // or we can add it in onDisconnect callback. 
  // But standard pattern often requires check. 
  // Actually NimBLE auto-advertising usually requires explicit start in callback or loop.
  // Let's safe guard it here similar to before.
  
  if (!deviceConnected && oldDeviceConnected) {
      delay(500); // Give the bluetooth stack the chance to get things ready
      pServer->getAdvertising()->start(); // restart advertising
      Serial.println("Start advertising");
      oldDeviceConnected = deviceConnected;
  }
  // Connecting (debounce)
  if (deviceConnected && !oldDeviceConnected) {
      oldDeviceConnected = deviceConnected;
  }
}
