"""
managers/alert_manager.py - Uyarı Yönetim Modülü
==================================================
Kaybolma algılama (hareketsizlik tabanlı) ve çarpışma/darbe uyarılarını
yönetir. Touch pin ve IMU verilerini kullanır.
"""
from machine import Pin, TouchPad
import time
from utils import logger
from config import (
    TOUCH_PIN, TOUCH_THRESHOLD,
    LOST_TIMEOUT_S, LOST_BUZZ_INTERVAL_S,
    IMPACT_ACCEL_G
)

_TAG = "ALERT"


class AlertManager:
    """Kaybolma ve darbe uyarı yöneticisi."""

    def __init__(self, buzzer_driver, bno_driver=None, activity_manager=None):
        self._buzzer = buzzer_driver
        self._bno = bno_driver
        self._activity_mgr = activity_manager

        # Touch pad
        try:
            self._touch = TouchPad(Pin(TOUCH_PIN))
            self._touch_available = True
            logger.debug(_TAG, "Touch GPIO{} hazir".format(TOUCH_PIN))
        except Exception as e:
            self._touch = None
            self._touch_available = False
            logger.warn(_TAG, "Touch baslatılamadı: {}".format(e))

        # Kaybolma durumu
        self._lost_mode = False
        self._last_lost_buzz = 0

        # Darbe durumu
        self._impact_detected = False
        self._last_impact_time = 0

        # Touch uyarı durumu
        self._touch_alert = False
        self._last_touch_time = 0
        self._touch_cooldown_ms = 2000  # 2 saniye soğuma süresi

        # Genel uyarı durumları
        self._alerts_enabled = True

    # =========================================================================
    # ANA GÜNCELLEME
    # =========================================================================

    def update(self):
        """
        Tüm uyarı durumlarını günceller. Ana döngüden düzenli çağrılmalıdır.
        
        Returns:
            dict: Aktif uyarılar
        """
        if not self._alerts_enabled:
            return {"lost": False, "impact": False, "touch": False}

        alerts = {
            "lost": self._check_lost(),
            "impact": self._check_impact(),
            "touch": self._check_touch()
        }

        return alerts

    # =========================================================================
    # KAYBOLMA ALGILAMA
    # =========================================================================

    def _check_lost(self):
        """
        Hareketsizlik tabanlı kaybolma kontrolü.
        Belirli süre hareketsiz kalınırsa kayıp modunu aktifler.
        """
        if not self._activity_mgr:
            return False

        idle_s = self._activity_mgr.get_idle_duration_s()

        if idle_s >= LOST_TIMEOUT_S:
            if not self._lost_mode:
                self._lost_mode = True
                logger.warn(_TAG, "KAYBOLMA ALARMI! {:.0f}s hareketsiz".format(idle_s))

            # Periyodik buzzer çal
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_lost_buzz) >= LOST_BUZZ_INTERVAL_S * 1000:
                self._last_lost_buzz = now
                if self._buzzer:
                    self._buzzer.pattern_lost_alert()

            return True
        else:
            if self._lost_mode:
                self._lost_mode = False
                logger.info(_TAG, "Kaybolma alarmi iptal edildi")
            return False

    # =========================================================================
    # DARBE / ÇARPIŞMA ALGILAMA
    # =========================================================================

    def _check_impact(self):
        """
        Yüksek ivme tabanlı darbe/çarpışma kontrolü.
        """
        if not self._bno:
            return False

        magnitude = self._bno.get_acceleration_magnitude()
        if magnitude is None:
            return False

        if magnitude >= IMPACT_ACCEL_G:
            now = time.ticks_ms()
            # Tekrarlayan uyarı önleme (3 saniyelik cooldown)
            if time.ticks_diff(now, self._last_impact_time) < 3000:
                return False

            self._impact_detected = True
            self._last_impact_time = now
            logger.warn(_TAG, "DARBE ALGILANDI! {:.1f}g".format(magnitude))

            if self._buzzer:
                self._buzzer.pattern_impact_alert()

            return True

        return False

    # =========================================================================
    # TOUCH PİN ALGILAMA
    # =========================================================================

    def _check_touch(self):
        """
        Touch pin ile çarpışma/dokunma algılama.
        """
        if not self._touch_available:
            return False

        try:
            touch_val = self._touch.read()

            if touch_val > TOUCH_THRESHOLD:
                now = time.ticks_ms()
                # Soğuma süresi kontrolü
                if time.ticks_diff(now, self._last_touch_time) < self._touch_cooldown_ms:
                    return False

                self._touch_alert = True
                self._last_touch_time = now
                logger.warn(_TAG, "TOUCH UYARISI! Deger: {}".format(touch_val))

                if self._buzzer:
                    self._buzzer.pattern_impact_alert()

                return True
        except:
            pass

        return False

    # =========================================================================
    # KONTROL
    # =========================================================================

    def enable_alerts(self):
        """Uyarıları etkinleştirir."""
        self._alerts_enabled = True
        logger.info(_TAG, "Uyarilar etkinlestirildi")

    def disable_alerts(self):
        """Uyarıları devre dışı bırakır."""
        self._alerts_enabled = False
        self._lost_mode = False
        logger.info(_TAG, "Uyarilar devre disi birakildi")

    def clear_impact(self):
        """Darbe bayrağını temizler."""
        self._impact_detected = False

    def clear_touch(self):
        """Touch bayrağını temizler."""
        self._touch_alert = False

    @property
    def is_lost(self):
        return self._lost_mode

    @property
    def has_impact(self):
        return self._impact_detected
