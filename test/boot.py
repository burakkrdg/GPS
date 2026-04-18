"""
boot.py - MicroPython Boot Dosyası
====================================
ESP32 açılışında ilk çalışan dosya.
Temel donanım testi ve sistemin sağlıklı olup olmadığını kontrol eder.
"""
import gc
import machine

# Bellek optimizasyonu
gc.collect()

# CPU frekansını ayarla (performans için 240MHz)
machine.freq(240000000)

print("=" * 50)
print("  GPS TAKIP SISTEMI v1.0")
print("  Boot baslatiliyor...")
print("  CPU: {} MHz".format(machine.freq() // 1000000))
print("  RAM: {} KB bos".format(gc.mem_free() // 1024))
print("=" * 50)
