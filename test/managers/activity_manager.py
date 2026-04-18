"""
managers/activity_manager.py - Aktivite Algılama Modülü
========================================================
BNO055 IMU verilerinden yürüme, koşma, hareketsizlik durumlarını algılar.
Kayma penceresi (sliding window) yöntemiyle gürültüyü filtreler.
"""
import time
from utils import logger
from config import (
    ACTIVITY_POLL_MS, ACTIVITY_WINDOW_SIZE,
    ACCEL_WALK_THRESHOLD, ACCEL_RUN_THRESHOLD, ACCEL_IDLE_THRESHOLD
)

_TAG = "ACTIVITY"

# Aktivite durumları
IDLE     = "IDLE"       # Hareketsiz
WALKING  = "WALKING"    # Yürüme
RUNNING  = "RUNNING"    # Koşma
UNKNOWN  = "UNKNOWN"    # Belirsiz


class ActivityManager:
    """IMU tabanlı aktivite algılama yöneticisi."""

    def __init__(self, bno_driver):
        self._bno = bno_driver

        # Kayma penceresi buffer (Circular buffer)
        self._window = [0.0] * ACTIVITY_WINDOW_SIZE
        self._window_idx = 0
        self._window_full = False

        # Durum
        self._current_activity = UNKNOWN
        self._last_activity = UNKNOWN
        self._activity_changed = False
        self._last_poll = 0

        # İstatistikler
        self._step_count = 0
        self._idle_start = 0        # Hareketsizlik başlangıcı
        self._idle_duration = 0     # Toplam hareketsizlik süresi (ms)

        logger.debug(_TAG, "Aktivite yoeneticisi hazir")

    # =========================================================================
    # ANA GÜNCELLEME
    # =========================================================================

    def update(self):
        """
        Sensörden veri okur ve aktiviteyi günceller.
        config.ACTIVITY_POLL_MS aralığında çağrılmalıdır.
        
        Returns:
            str: Mevcut aktivite durumu
        """
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_poll) < ACTIVITY_POLL_MS:
            return self._current_activity
        self._last_poll = now

        # İvme büyüklüğü oku (g cinsinden)
        magnitude = self._bno.get_acceleration_magnitude()
        if magnitude is None:
            return self._current_activity

        # Pencereye ekle
        self._window[self._window_idx] = magnitude
        self._window_idx = (self._window_idx + 1) % ACTIVITY_WINDOW_SIZE
        if self._window_idx == 0:
            self._window_full = True

        # Yeterli veri toplandıysa analiz et
        if not self._window_full:
            return UNKNOWN

        avg = self._calculate_average()
        peak = max(self._window)

        # Aktivite sınıflandırma
        self._last_activity = self._current_activity

        if peak >= ACCEL_RUN_THRESHOLD and avg >= ACCEL_WALK_THRESHOLD:
            self._current_activity = RUNNING
            self._reset_idle()
        elif avg >= ACCEL_WALK_THRESHOLD:
            self._current_activity = WALKING
            self._reset_idle()
        elif avg <= ACCEL_IDLE_THRESHOLD:
            self._current_activity = IDLE
            if self._idle_start == 0:
                self._idle_start = now
            self._idle_duration = time.ticks_diff(now, self._idle_start)
        else:
            # Geçiş bölgesi - önceki durumu koru
            pass

        # Durum değişimi algılama
        if self._current_activity != self._last_activity:
            self._activity_changed = True
            logger.info(_TAG, "Aktivite: {} -> {}".format(
                self._last_activity, self._current_activity))

        return self._current_activity

    # =========================================================================
    # YARDIMCI METOTLAR
    # =========================================================================

    def _calculate_average(self):
        """Pencere ortalamasını hesaplar."""
        return sum(self._window) / ACTIVITY_WINDOW_SIZE

    def _reset_idle(self):
        """Hareketsizlik sayacını sıfırlar."""
        self._idle_start = 0
        self._idle_duration = 0

    # =========================================================================
    # DURUM SORGULAMA
    # =========================================================================

    def has_activity_changed(self):
        """Aktivite değişti mi? (Bir kez True döner, sonra sıfırlar)."""
        if self._activity_changed:
            self._activity_changed = False
            return True
        return False

    def get_idle_duration_s(self):
        """Hareketsizlik süresini saniye olarak döndürür."""
        return self._idle_duration / 1000

    @property
    def activity(self):
        return self._current_activity

    @property
    def is_idle(self):
        return self._current_activity == IDLE

    @property
    def is_walking(self):
        return self._current_activity == WALKING

    @property
    def is_running(self):
        return self._current_activity == RUNNING
