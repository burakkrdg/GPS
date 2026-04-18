"""
managers/power_manager.py - Güç Yönetim Modülü
================================================
Basit ve güvenilir uyku/uyanma sistemi.

- Thread ile arka planda buton izleme (ana döngüyü bloklamaz)
- Uyku = modüller kapatılır, LED söner, basit döngüde buton beklenir
- Uyanma = buton algılanır, modüller açılır
- USB bağlantısı HİÇBİR ZAMAN kopmaz (lightsleep yok)
"""
from machine import Pin
import _thread
import time
from utils import logger
from config import (
    POWER_LED_PIN,
    STATE_BOOTING, STATE_RUNNING, STATE_SLEEPING
)

_TAG = "POWER"
_BTN_PIN = 0          # Boot butonu (active LOW)
_HOLD_MS = 1500       # Basılı tutma süresi (1.5 saniye)


class PowerManager:

    def __init__(self, battery_driver=None, buzzer_driver=None):
        self._led = Pin(POWER_LED_PIN, Pin.OUT)
        self._led.value(0)
        self._btn = Pin(_BTN_PIN, Pin.IN, Pin.PULL_UP)
        self._battery = battery_driver
        self._buzzer = buzzer_driver
        self._state = STATE_BOOTING
        self._sleep_requested = False
        self._thread_running = False

    # ── LED ──────────────────────────────────────────

    def led_on(self):
        self._led.value(1)

    def led_off(self):
        self._led.value(0)

    def led_blink(self, count=3, on_ms=200, off_ms=200):
        for _ in range(count):
            self._led.value(1)
            time.sleep_ms(on_ms)
            self._led.value(0)
            time.sleep_ms(off_ms)

    # ── BUTON THREAD ─────────────────────────────────

    def start_button_thread(self):
        if self._thread_running:
            return
        self._thread_running = True
        _thread.start_new_thread(self._btn_watcher, ())
        logger.info(_TAG, "Buton thread baslatildi")

    def stop_button_thread(self):
        self._thread_running = False
        time.sleep_ms(200)

    def _btn_watcher(self):
        """Arka plan thread'i: butonu sürekli izler."""
        while self._thread_running:
            try:
                if self._btn.value() == 0:  # Buton basıldı
                    if self._wait_long_press():
                        self._sleep_requested = True
            except:
                pass
            time.sleep_ms(50)

    def _wait_long_press(self):
        """
        Buton basılıyken bekler.
        1.5sn basılı tutulursa True döner.
        LED yanıp sönerek geri bildirim verir.
        """
        start = time.ticks_ms()

        while self._btn.value() == 0:
            held = time.ticks_diff(time.ticks_ms(), start)

            # LED geri bildirimi (500ms sonra başla)
            if held > 400:
                self._led.value(1 if (held // 100) % 2 == 0 else 0)

            # Uzun basma tamamlandı
            if held >= _HOLD_MS:
                # Onay blink
                for _ in range(3):
                    self._led.value(1)
                    time.sleep_ms(60)
                    self._led.value(0)
                    time.sleep_ms(60)
                # Butonun bırakılmasını bekle
                while self._btn.value() == 0:
                    time.sleep_ms(50)
                return True

            time.sleep_ms(30)

        # Kısa basım - LED'i geri yükle
        if self._state == STATE_RUNNING:
            self._led.value(1)
        return False

    # ── ANA DÖNGÜ KONTROLÜ ───────────────────────────

    def check_sleep_request(self):
        if self._sleep_requested:
            self._sleep_requested = False
            return True
        return False

    # ── UYKU / UYANMA ───────────────────────────────

    def enter_sleep(self, shutdown_callback=None):
        """
        Sistemi uyku moduna alır.
        USB bağlantısı korunur (lightsleep kullanılmaz).
        """
        logger.info(_TAG, ">>> UYKU MODUNA GECILIYOR <<<")

        # Thread durdur
        self.stop_button_thread()
        self._state = STATE_SLEEPING

        # Kapanış sesi
        if self._buzzer:
            self._buzzer.pattern_shutdown()

        # Modülleri kapat
        if shutdown_callback:
            shutdown_callback()

        # LED söndür
        self.led_off()

        # Buton bırakılmasını bekle
        while self._btn.value() == 0:
            time.sleep_ms(50)
        time.sleep_ms(300)

        logger.info(_TAG, "Uyku modunda - buton ile uyandir")

        # ── BASİT UYKU DÖNGÜSÜ ──
        # Hiçbir şey yapmadan buton bekle
        while True:
            time.sleep_ms(100)

            if self._btn.value() == 0:
                if self._wait_long_press():
                    break  # Uzun basma → uyan

        # ── UYANMA ──
        self._state = STATE_RUNNING
        self._sleep_requested = False
        self.led_on()

        if self._buzzer:
            self._buzzer.pattern_boot()

        # Thread'i tekrar başlat
        self.start_button_thread()

        logger.info(_TAG, ">>> SISTEM UYANDI <<<")
        return True

    # ── PİL KONTROL ──────────────────────────────────

    def check_battery(self):
        if not self._battery:
            return "OK"
        status = self._battery.get_status()
        level = status["level"]
        if level == "CRITICAL":
            logger.error(_TAG, "KRITIK PIL: {:.2f}V (%{})".format(
                status["voltage"], status["percent"]))
            if self._buzzer:
                self._buzzer.pattern_low_battery()
        elif level == "LOW":
            logger.warn(_TAG, "Dusuk pil: {:.2f}V (%{})".format(
                status["voltage"], status["percent"]))
        return level

    # ── DURUM ────────────────────────────────────────

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def is_running(self):
        return self._state == STATE_RUNNING
