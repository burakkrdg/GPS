"""
drivers/battery.py - Pil Voltaj Ölçüm Sürücüsü
=================================================
Voltaj bölücü üzerinden ADC ile pil voltajını ölçer ve yüzde hesaplar.
Devre: VBAT --- [R1=220K] --- ADC_PIN --- [R2=120K] --- GND
"""
from machine import ADC, Pin
import time
from utils import logger
from config import (
    BATTERY_ADC_PIN, BATTERY_R1, BATTERY_R2,
    ADC_VREF, ADC_RESOLUTION,
    BATTERY_FULL_V, BATTERY_LOW_V, BATTERY_CRITICAL_V
)

_TAG = "BATTERY"

# LiPo voltaj-kapasite eğrisi (yaklaşık)
_VOLTAGE_CURVE = [
    (4.20, 100),
    (4.10, 90),
    (4.00, 80),
    (3.90, 65),
    (3.80, 50),
    (3.70, 35),
    (3.60, 20),
    (3.50, 10),
    (3.40, 5),
    (3.30, 2),
    (3.00, 0),
]


class Battery:
    """Pil voltaj ölçümü ve durum izleme."""

    def __init__(self):
        self._adc = ADC(Pin(BATTERY_ADC_PIN))
        self._adc.atten(ADC.ATTN_11DB)    # 0-3.3V aralığı
        self._adc.width(ADC.WIDTH_12BIT)   # 12-bit çözünürlük

        # Voltaj bölücü oranı: Vout = Vbat * R2 / (R1 + R2)
        self._divider_ratio = (BATTERY_R1 + BATTERY_R2) / BATTERY_R2

        self._samples = 10   # Ortalama alma için örnek sayısı
        self._last_voltage = 0.0
        self._last_percent = 0

        logger.debug(_TAG, "ADC GPIO{} hazir (bolucu oran: {:.2f})".format(
            BATTERY_ADC_PIN, self._divider_ratio))

    # =========================================================================
    # ÖLÇÜM
    # =========================================================================

    def read_voltage(self):
        """
        Pil voltajını okur (çoklu örnekleme ile ortalama).
        
        Returns:
            float: Pil voltajı (V)
        """
        total = 0
        for _ in range(self._samples):
            total += self._adc.read()
            time.sleep_ms(2)

        avg_raw = total / self._samples
        adc_voltage = (avg_raw / ADC_RESOLUTION) * ADC_VREF
        battery_voltage = adc_voltage * self._divider_ratio

        self._last_voltage = round(battery_voltage, 2)
        return self._last_voltage

    def read_percentage(self):
        """
        Pil yüzdesini hesaplar (voltaj-kapasite eğrisinden).
        
        Returns:
            int: Pil yüzdesi (0-100)
        """
        voltage = self.read_voltage()

        # Eğriden yüzde hesapla (doğrusal interpolasyon)
        if voltage >= _VOLTAGE_CURVE[0][0]:
            self._last_percent = 100
            return 100
        if voltage <= _VOLTAGE_CURVE[-1][0]:
            self._last_percent = 0
            return 0

        for i in range(len(_VOLTAGE_CURVE) - 1):
            v_high, p_high = _VOLTAGE_CURVE[i]
            v_low, p_low = _VOLTAGE_CURVE[i + 1]

            if v_low <= voltage <= v_high:
                ratio = (voltage - v_low) / (v_high - v_low)
                percent = int(p_low + ratio * (p_high - p_low))
                self._last_percent = percent
                return percent

        self._last_percent = 0
        return 0

    # =========================================================================
    # DURUM KONTROL
    # =========================================================================

    def is_low(self):
        """Pil düşük mü?"""
        return self._last_voltage < BATTERY_LOW_V and self._last_voltage > 0

    def is_critical(self):
        """Pil kritik seviyede mi?"""
        return self._last_voltage < BATTERY_CRITICAL_V and self._last_voltage > 0

    def get_status(self):
        """
        Tam pil durumu sözlüğü döndürür.
        
        Returns:
            dict: {voltage, percent, level}
        """
        voltage = self.read_voltage()
        percent = self.read_percentage()

        if voltage >= BATTERY_FULL_V - 0.05:
            level = "FULL"
        elif voltage >= BATTERY_LOW_V:
            level = "NORMAL"
        elif voltage >= BATTERY_CRITICAL_V:
            level = "LOW"
        else:
            level = "CRITICAL"

        return {
            "voltage": voltage,
            "percent": percent,
            "level": level
        }

    @property
    def voltage(self):
        return self._last_voltage

    @property
    def percent(self):
        return self._last_percent
