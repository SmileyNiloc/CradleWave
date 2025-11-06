// Simple SPI test for BGT60TRxx
#include <Arduino.h>
#include <SPI.h>

#define CS_PIN    7
#define RESET_PIN 6

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    
    Serial.println("\n=== BGT60TRxx SPI Communication Test ===");
    Serial.println("MKR WiFi 1010 - SPI Pins: MOSI=8, MISO=10, SCK=9");
    Serial.print("CS Pin: "); Serial.println(CS_PIN);
    Serial.print("Reset Pin: "); Serial.println(RESET_PIN);
    Serial.println();
    
    // Initialize SPI and pins
    SPI.begin();
    pinMode(CS_PIN, OUTPUT);
    pinMode(RESET_PIN, OUTPUT);
    digitalWrite(CS_PIN, HIGH);
    digitalWrite(RESET_PIN, HIGH);
    
    delay(100);
    
    // Hardware reset
    Serial.println("Performing hardware reset...");
    digitalWrite(CS_PIN, HIGH);
    digitalWrite(RESET_PIN, LOW);
    delay(10);
    digitalWrite(RESET_PIN, HIGH);
    delay(100);
    Serial.println("Reset complete\n");
    
    // Try to read CHIP_ID register (address 0x02)
    Serial.println("Attempting to read CHIP_ID register (0x02)...");
    
    SPISettings settings(1000000, MSBFIRST, SPI_MODE0);
    SPI.beginTransaction(settings);
    
    // Prepare read command
    // Format: 7-bit address + 1-bit R/W (0=read)
    uint32_t cmd = 0x02 << 25;  // Address 0x02 in bits [31:25], R/W=0
    
    uint8_t tx[4], rx[4];
    tx[0] = (cmd >> 24) & 0xFF;
    tx[1] = (cmd >> 16) & 0xFF;
    tx[2] = (cmd >> 8) & 0xFF;
    tx[3] = cmd & 0xFF;
    
    Serial.print("TX bytes: ");
    for (int i = 0; i < 4; i++) {
        Serial.print("0x");
        if (tx[i] < 0x10) Serial.print("0");
        Serial.print(tx[i], HEX);
        Serial.print(" ");
    }
    Serial.println();
    
    digitalWrite(CS_PIN, LOW);
    delayMicroseconds(1);
    
    for (int i = 0; i < 4; i++) {
        rx[i] = SPI.transfer(tx[i]);
    }
    
    delayMicroseconds(1);
    digitalWrite(CS_PIN, HIGH);
    SPI.endTransaction();
    
    Serial.print("RX bytes: ");
    for (int i = 0; i < 4; i++) {
        Serial.print("0x");
        if (rx[i] < 0x10) Serial.print("0");
        Serial.print(rx[i], HEX);
        Serial.print(" ");
    }
    Serial.println();
    
    uint32_t chip_id = (rx[1] << 16) | (rx[2] << 8) | rx[3];
    chip_id &= 0x00FFFFFF;  // 24-bit data
    
    Serial.print("\nChip ID: 0x");
    Serial.println(chip_id, HEX);
    
    uint8_t digital_id = (chip_id >> 16) & 0xFF;
    uint8_t rf_id = (chip_id >> 8) & 0xFF;
    
    Serial.print("Digital ID: 0x");
    Serial.println(digital_id, HEX);
    Serial.print("RF ID: 0x");
    Serial.println(rf_id, HEX);
    
    if (chip_id == 0 || chip_id == 0xFFFFFF) {
        Serial.println("\nWARNING: Invalid chip ID!");
        Serial.println("Possible issues:");
        Serial.println("  - Sensor not connected");
        Serial.println("  - Wrong pin assignments");
        Serial.println("  - Power supply issue");
        Serial.println("  - SPI wiring problem");
    } else {
        Serial.println("\nChip ID looks valid!");
    }
}

void loop() {
    delay(5000);
    Serial.println("Test complete. Reset to run again.");
}
