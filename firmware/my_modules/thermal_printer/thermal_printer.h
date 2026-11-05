#pragma once
#include <Arduino.h>
#include <HardwareSerial.h>

// Rate-limited ESC/POS output for a TTL thermal printer.
// The host sends base64 chunks; update() drains them without ever blocking loop().
class ThermalPrinter {
public:
    static constexpr size_t QUEUE_BYTES = 16384;
    static constexpr size_t MAX_CHUNK_BYTES = 2400;

    explicit ThermalPrinter(int txPin);

    void begin();
    void update();

    // Returns nullptr on success, or the reason the chunk was not queued.
    const char* enqueueBase64(const String& encoded);
    void configure(uint32_t baud, uint32_t bytesPerSec);
    void cancel();
    size_t pending() const { return _count; }

private:
    int _txPin;
    uint32_t _baud = 9600;
    uint32_t _bytesPerSec = 900;
    uint8_t* _queue = nullptr;
    size_t _head = 0;
    size_t _count = 0;
    uint32_t _lastDrainMs = 0;
    uint32_t _credit = 0;  // bytes per 1000 that the rate limit currently allows
};
