#include "thermal_printer.h"
#include <mbedtls/base64.h>

ThermalPrinter::ThermalPrinter(int txPin) : _txPin(txPin) {}

void ThermalPrinter::begin() {
    if (!_queue) _queue = (uint8_t*)malloc(QUEUE_BYTES);
    // RX is -1: the printer's TX line stays disconnected, see module.yaml.
    Serial1.begin(_baud, SERIAL_8N1, -1, _txPin);
    _lastDrainMs = millis();
}

void ThermalPrinter::configure(uint32_t baud, uint32_t bytesPerSec) {
    if (baud > 0 && baud != _baud) {
        _baud = baud;
        Serial1.updateBaudRate(_baud);
    }
    if (bytesPerSec > 0) _bytesPerSec = bytesPerSec;
}

void ThermalPrinter::cancel() {
    _head = 0;
    _count = 0;
    _credit = 0;
}

const char* ThermalPrinter::enqueueBase64(const String& encoded) {
    if (!_queue) return "no memory for the print queue";

    static uint8_t chunk[MAX_CHUNK_BYTES];
    size_t decoded = 0;
    int rc = mbedtls_base64_decode(chunk, sizeof(chunk), &decoded,
                                   (const unsigned char*)encoded.c_str(), encoded.length());
    if (rc != 0) return "bad base64, or the chunk is over 2400 bytes";
    if (decoded > QUEUE_BYTES - _count) return "busy";

    size_t tail = (_head + _count) % QUEUE_BYTES;
    size_t first = min(decoded, QUEUE_BYTES - tail);
    memcpy(_queue + tail, chunk, first);
    memcpy(_queue, chunk + first, decoded - first);
    _count += decoded;
    return nullptr;
}

void ThermalPrinter::update() {
    uint32_t now = millis();
    uint32_t elapsed = now - _lastDrainMs;
    _lastDrainMs = now;

    if (_count == 0) {
        _credit = 0;  // an idle printer does not save up a burst
        return;
    }

    _credit += elapsed * _bytesPerSec;
    size_t allowed = _credit / 1000;
    if (allowed == 0) return;

    size_t room = Serial1.availableForWrite();
    size_t send = min(min(allowed, _count), room);
    send = min(send, QUEUE_BYTES - _head);  // one contiguous run per loop pass
    if (send == 0) return;

    Serial1.write(_queue + _head, send);
    _head = (_head + send) % QUEUE_BYTES;
    _count -= send;
    _credit -= send * 1000;
}
