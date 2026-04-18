"""
test_touch.py - Touch Sensör Test Kodu
========================================
GPIO 9 üzerindeki touch sensörün değerlerini okur.
Dokunma ve dokunmama durumlarındaki değer aralığını gösterir.
"""
from machine import Pin, TouchPad
import time

TOUCH_PIN = 9
LED_PIN = 13

print("=" * 40)
print("  TOUCH SENSOR TEST - GPIO{} + LED GPIO{}".format(TOUCH_PIN, LED_PIN))
print("=" * 40)

touch = TouchPad(Pin(TOUCH_PIN))
led = Pin(LED_PIN, Pin.OUT)
led.value(0)

# İstatistikler
min_val = 99999
max_val = 0
readings = []

print("\nDegerleri okuyorum... (Ctrl+C ile dur)")
print("Dokunun ve birakin, farki gorun.\n")
print("{:<10} {:<10} {:<10} {:<10}".format("DEGER", "MIN", "MAX", "DURUM"))
print("-" * 40)

try:
    while True:
        val = touch.read()
        
        if val < min_val:
            min_val = val
        if val > max_val:
            max_val = val
        
        # Son 5 okumayı tut (ortalama için)
        readings.append(val)
        if len(readings) > 5:
            readings.pop(0)
        avg = sum(readings) // len(readings)
        
        # Basit durum tahmini
        # (İlk çalıştırmada dokunmadan birkaç saniye bekleyin,
        #  sonra dokunun - MIN/MAX değerlerden eşiği anlayacaksınız)
        mid = (min_val + max_val) // 2 if max_val > min_val else 99999
        
        if avg > mid and max_val - min_val > 50:
            durum = "<<< DOKUNUYOR"
            led.value(1)
        else:
            durum = "    bos"
            led.value(0)
        
        print("\r{:<10} {:<10} {:<10} {}      ".format(val, min_val, max_val, durum), end="")
        
        time.sleep_ms(100)

except KeyboardInterrupt:
    print("\n\n" + "=" * 40)
    print("  SONUCLAR")
    print("=" * 40)
    print("  MIN (dokunma):    {}".format(min_val))
    print("  MAX (bos):        {}".format(max_val))
    
    if max_val > min_val:
        threshold = (min_val + max_val) // 2
        print("  ONERILEN ESIK:    {}".format(threshold))
        print("\n  config.py icin:")
        print("  TOUCH_PIN       = {}".format(TOUCH_PIN))
        print("  TOUCH_THRESHOLD = {}".format(threshold))
    
    print("=" * 40)
