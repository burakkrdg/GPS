"""
drivers/buzzer.py - Buzzer Kontrol Sürücüsü
=============================================
PWM tabanlı buzzer kontrolü. Farklı uyarı kalıpları (pattern) desteği sunar.
"""
from machine import Pin, PWM
import time
from utils import logger
from config import BUZZER_PIN

_TAG = "BUZZER"


class Buzzer:
    """PWM tabanlı buzzer sürücüsü."""

    def __init__(self):
        self._pin = Pin(BUZZER_PIN, Pin.OUT)
        self._pwm = None
        self._pin.value(0)  # Başlangıçta sessiz
        logger.debug(_TAG, "Buzzer GPIO{} uzerinde hazir".format(BUZZER_PIN))

    # =========================================================================
    # TEMEL KONTROL
    # =========================================================================

    def beep(self, freq=2000, duration_ms=200):
        """Belirli frekansta ve sürede tek bip."""
        try:
            self._pwm = PWM(self._pin)
            self._pwm.freq(freq)
            self._pwm.duty_u16(32768)  # %50 duty cycle (ESP32-S3 uyumlu)
            time.sleep_ms(duration_ms)
            self._pwm.deinit()
            self._pin = Pin(BUZZER_PIN, Pin.OUT)
            self._pin.value(0)
        except Exception as e:
            logger.error(_TAG, "Beep hatasi: {}".format(e))
            try:
                self._pin = Pin(BUZZER_PIN, Pin.OUT)
                self._pin.value(0)
            except:
                pass

    def off(self):
        """Buzzer'ı kapatır."""
        try:
            if self._pwm:
                self._pwm.deinit()
        except:
            pass
        self._pin.value(0)

    # =========================================================================
    # UYARI KALIPLARİ (PATTERNS)
    # =========================================================================

    def pattern_boot(self):
        """Sistem açılış sesi: kısa-kısa-uzun."""
        self.beep(1000, 100)
        time.sleep_ms(80)
        self.beep(1500, 100)
        time.sleep_ms(80)
        self.beep(2000, 300)

    def pattern_shutdown(self):
        """Sistem kapanış sesi: uzun-kısa-kısa."""
        self.beep(2000, 300)
        time.sleep_ms(80)
        self.beep(1500, 100)
        time.sleep_ms(80)
        self.beep(800, 100)

    def pattern_gps_fix(self):
        """GPS konum bulundu sesi: üç kısa yüksek ton."""
        for _ in range(3):
            self.beep(2500, 80)
            time.sleep_ms(60)

    def pattern_lost_alert(self):
        """Kaybolma alarmı: SOS benzeri uzun sürekli."""
        # 3 kısa
        for _ in range(3):
            self.beep(2000, 150)
            time.sleep_ms(100)
        time.sleep_ms(200)
        # 3 uzun
        for _ in range(3):
            self.beep(2000, 400)
            time.sleep_ms(100)
        time.sleep_ms(200)
        # 3 kısa
        for _ in range(3):
            self.beep(2000, 150)
            time.sleep_ms(100)

    def pattern_impact_alert(self):
        """Darbe/çarpışma uyarısı: hızlı yükselen ton."""
        for f in range(800, 3000, 200):
            self.beep(f, 50)
            time.sleep_ms(30)

    def pattern_low_battery(self):
        """Düşük pil uyarısı: iki alçak ton."""
        self.beep(500, 300)
        time.sleep_ms(200)
        self.beep(400, 500)

    def pattern_success(self):
        """Başarılı işlem sesi."""
        self.beep(1000, 100)
        time.sleep_ms(50)
        self.beep(2000, 200)

    def pattern_error(self):
        """Hata sesi: düşük tekrarlayan ton."""
        for _ in range(3):
            self.beep(300, 200)
            time.sleep_ms(150)

    # =========================================================================
    # MELODY (İsteğe bağlı melodi çalma)
    # =========================================================================

    def play_melody(self, notes):
        """
        Not dizisi çalar.
        
        Args:
            notes: [(frekans_hz, süre_ms, ara_ms), ...] listesi
        """
        for freq, dur, gap in notes:
            if freq > 0:
                self.beep(freq, dur)
            else:
                time.sleep_ms(dur)
            time.sleep_ms(gap)
