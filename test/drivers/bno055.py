"""
drivers/bno055.py - BNO055 IMU Sensör Sürücüsü
=================================================
BNO055 9-eksen IMU sensöründen ivmeölçer, jiroskop ve euler açı verilerini
okur. Aktivite algılama için ham veri sağlar.
"""
from machine import SoftI2C, Pin
import time
import struct
from utils import logger
from config import (
    BNO_SDA_PIN, BNO_SCL_PIN, BNO_I2C_ID,
    BNO_I2C_FREQ, BNO_ADDRESS
)

_TAG = "BNO055"

# =============================================================================
# BNO055 REGISTER ADRESLERİ
# =============================================================================
_REG_CHIP_ID        = 0x00
_REG_ACC_X_LSB      = 0x08
_REG_GYR_X_LSB      = 0x14
_REG_EUL_HEADING    = 0x1A
_REG_LINEAR_ACC_X   = 0x28
_REG_GRAVITY_X      = 0x2E
_REG_CALIB_STAT     = 0x35
_REG_SYS_STATUS     = 0x39
_REG_OPR_MODE       = 0x3D
_REG_PWR_MODE       = 0x3E
_REG_SYS_TRIGGER    = 0x3F
_REG_UNIT_SEL       = 0x3B

# Çalışma modları
_MODE_CONFIG        = 0x00
_MODE_NDOF          = 0x0C  # 9-axis fusion
_MODE_IMU           = 0x08  # Accel + Gyro fusion
_MODE_AMG           = 0x07  # Accel + Mag + Gyro (no fusion)

# Güç modları
_PWR_NORMAL         = 0x00
_PWR_LOW            = 0x01
_PWR_SUSPEND        = 0x02

# Beklenen Chip ID
_CHIP_ID_VALUE      = 0xA0

# Birim dönüşüm faktörleri
_ACC_SCALE          = 1.0 / 100.0   # m/s² -> 100 LSB/m/s²
_GYR_SCALE          = 1.0 / 16.0    # dps
_EUL_SCALE          = 1.0 / 16.0    # derece
_G_TO_MS2           = 9.80665


class BNO055:
    """BNO055 9-eksen IMU sensör sürücüsü."""

    def __init__(self):
        self._i2c = None
        self._addr = BNO_ADDRESS
        self._initialized = False

    # =========================================================================
    # BAŞLATMA / KAPATMA
    # =========================================================================

    def init(self):
        """Sensörü başlatır ve NDOF moduna geçirir."""
        logger.info(_TAG, "I2C baslatiliyor (SDA={}, SCL={})...".format(
            BNO_SDA_PIN, BNO_SCL_PIN))

        try:
            self._i2c = SoftI2C(
                sda=Pin(BNO_SDA_PIN),
                scl=Pin(BNO_SCL_PIN),
                freq=100000  # 100kHz - baslangicta dusuk, kararlı
            )

            # I2C cihaz taraması
            devices = self._i2c.scan()
            if self._addr not in devices:
                logger.error(_TAG, "Cihaz bulunamadi! Bulunan: {}".format(
                    [hex(d) for d in devices]))
                return False

            # Chip ID doğrulama
            chip_id = self._read_byte(_REG_CHIP_ID)
            if chip_id != _CHIP_ID_VALUE:
                logger.error(_TAG, "Yanlis chip ID: 0x{:02X}".format(chip_id))
                return False

            logger.info(_TAG, "Chip ID dogrulandi: 0x{:02X}".format(chip_id))

            # CONFIG moduna geç
            self._set_mode(_MODE_CONFIG)
            time.sleep_ms(25)

            # Reset
            self._write_byte(_REG_SYS_TRIGGER, 0x20)
            time.sleep_ms(700)

            # Reset sonrası tekrar chip ID kontrolü
            retries = 0
            while retries < 10:
                try:
                    chip_id = self._read_byte(_REG_CHIP_ID)
                    if chip_id == _CHIP_ID_VALUE:
                        break
                except:
                    pass
                retries += 1
                time.sleep_ms(100)

            # Normal güç modu
            self._write_byte(_REG_PWR_MODE, _PWR_NORMAL)
            time.sleep_ms(10)

            # Ünite ayarları: m/s², derece, santigrat
            self._write_byte(_REG_UNIT_SEL, 0x00)

            # SYS_TRIGGER sıfırla
            self._write_byte(_REG_SYS_TRIGGER, 0x00)
            time.sleep_ms(10)

            # NDOF moduna geç (tam 9-eksen füzyon)
            self._set_mode(_MODE_NDOF)
            time.sleep_ms(20)

            self._initialized = True
            logger.info(_TAG, "BNO055 basarıyla baslatildi (NDOF modu)")
            return True

        except Exception as e:
            logger.error(_TAG, "Baslatma hatasi: {}".format(e))
            return False

    def shutdown(self):
        """Sensörü uyku moduna alır."""
        if not self._initialized:
            return

        try:
            self._set_mode(_MODE_CONFIG)
            time.sleep_ms(25)
            self._write_byte(_REG_PWR_MODE, _PWR_SUSPEND)
            logger.info(_TAG, "Sensor uyku moduna alindi")
        except:
            pass

        self._initialized = False

    # =========================================================================
    # VERİ OKUMA
    # =========================================================================

    def get_acceleration(self):
        """
        Lineer ivme verisi okur (yerçekimi hariç).
        
        Returns:
            tuple: (x, y, z) m/s² cinsinden veya None
        """
        if not self._initialized:
            return None
        try:
            data = self._read_bytes(_REG_LINEAR_ACC_X, 6)
            x, y, z = struct.unpack('<hhh', data)
            return (x * _ACC_SCALE, y * _ACC_SCALE, z * _ACC_SCALE)
        except:
            return None

    def get_raw_acceleration(self):
        """
        Ham ivmeölçer verisi okur (yerçekimi dahil).
        
        Returns:
            tuple: (x, y, z) m/s² cinsinden veya None
        """
        if not self._initialized:
            return None
        try:
            data = self._read_bytes(_REG_ACC_X_LSB, 6)
            x, y, z = struct.unpack('<hhh', data)
            return (x * _ACC_SCALE, y * _ACC_SCALE, z * _ACC_SCALE)
        except:
            return None

    def get_gyroscope(self):
        """
        Jiroskop verisi okur.
        
        Returns:
            tuple: (x, y, z) derece/saniye cinsinden veya None
        """
        if not self._initialized:
            return None
        try:
            data = self._read_bytes(_REG_GYR_X_LSB, 6)
            x, y, z = struct.unpack('<hhh', data)
            return (x * _GYR_SCALE, y * _GYR_SCALE, z * _GYR_SCALE)
        except:
            return None

    def get_euler(self):
        """
        Euler açıları okur.
        
        Returns:
            tuple: (heading, roll, pitch) derece cinsinden veya None
        """
        if not self._initialized:
            return None
        try:
            data = self._read_bytes(_REG_EUL_HEADING, 6)
            h, r, p = struct.unpack('<hhh', data)
            return (h * _EUL_SCALE, r * _EUL_SCALE, p * _EUL_SCALE)
        except:
            return None

    def get_gravity(self):
        """
        Yerçekimi vektörü okur.
        
        Returns:
            tuple: (x, y, z) m/s² cinsinden veya None
        """
        if not self._initialized:
            return None
        try:
            data = self._read_bytes(_REG_GRAVITY_X, 6)
            x, y, z = struct.unpack('<hhh', data)
            return (x * _ACC_SCALE, y * _ACC_SCALE, z * _ACC_SCALE)
        except:
            return None

    def get_acceleration_magnitude(self):
        """
        Toplam lineer ivme büyüklüğünü hesaplar (g cinsinden).
        Aktivite algılama için kullanılır.
        
        Returns:
            float: İvme büyüklüğü (g) veya None
        """
        acc = self.get_acceleration()
        if acc is None:
            return None
        import math
        magnitude = math.sqrt(acc[0]**2 + acc[1]**2 + acc[2]**2)
        return magnitude / _G_TO_MS2  # m/s² -> g

    # =========================================================================
    # KALİBRASYON
    # =========================================================================

    def get_calibration_status(self):
        """
        Kalibrasyon durumunu okur.
        
        Returns:
            dict: {sys, gyro, accel, mag} 0-3 arası (3=kalibre)
        """
        if not self._initialized:
            return None
        try:
            cal = self._read_byte(_REG_CALIB_STAT)
            return {
                "sys":   (cal >> 6) & 0x03,
                "gyro":  (cal >> 4) & 0x03,
                "accel": (cal >> 2) & 0x03,
                "mag":   cal & 0x03
            }
        except:
            return None

    def is_calibrated(self):
        """Tüm sensörlerin kalibre olup olmadığını kontrol eder."""
        cal = self.get_calibration_status()
        if cal is None:
            return False
        return cal["sys"] >= 2 and cal["gyro"] >= 2

    # =========================================================================
    # DAHİLİ I2C İŞLEMLERİ
    # =========================================================================

    def _read_byte(self, reg):
        return self._i2c.readfrom_mem(self._addr, reg, 1)[0]

    def _read_bytes(self, reg, length):
        return self._i2c.readfrom_mem(self._addr, reg, length)

    def _write_byte(self, reg, value):
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))

    def _set_mode(self, mode):
        self._write_byte(_REG_OPR_MODE, mode)

    @property
    def initialized(self):
        return self._initialized
