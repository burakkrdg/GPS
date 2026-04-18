"""
drivers/sim7500e.py - SIM7500E GPS/GSM Modül Sürücüsü
=======================================================
SIM7500E modülünün donanım kontrolü, AT komut iletişimi ve GPS veri çözümleme
işlevlerini barındırır.
"""
from machine import UART, Pin
import time
from utils import logger
from config import (
    SIM_UART_ID, SIM_UART_BAUD, SIM_TX_PIN, SIM_RX_PIN,
    SIM_PWR_KEY_PIN, SIM_EN_PIN, SIM_UART_RXBUF, GPS_BOOT_TIMEOUT_S
)

_TAG = "SIM7500E"


class SIM7500E:
    """SIM7500E GPS/GSM modül sürücüsü."""

    def __init__(self):
        self._uart = None
        self._en_pin = None
        self._pwr_key = None
        self._gps_active = False
        self._first_fix = False
        self._boot_ticks = 0

    # =========================================================================
    # DONANIM KONTROL
    # =========================================================================

    def init_hardware(self):
        """Modül donanımını başlatır. Zaten açıksa PWR KEY tetiklemez."""
        logger.info(_TAG, "Donanim baslatiliyor...")
        self._boot_ticks = time.ticks_ms()

        # Enable pin - Voltaj regülatörü
        self._en_pin = Pin(SIM_EN_PIN, Pin.OUT)
        self._en_pin.value(1)
        time.sleep(0.5)

        # PWR KEY pinini hazırla (henüz tetikleme)
        self._pwr_key = Pin(SIM_PWR_KEY_PIN, Pin.OUT)
        self._pwr_key.value(1)

        # UART başlat (AT kontrolü için önce UART lazım)
        self._uart = UART(
            SIM_UART_ID,
            baudrate=SIM_UART_BAUD,
            tx=SIM_TX_PIN,
            rx=SIM_RX_PIN,
            timeout=1000,
            rxbuf=SIM_UART_RXBUF
        )

        # Modül zaten açık mı kontrol et (birkaç AT dene)
        already_on = False
        for _ in range(3):
            resp = self.send_at("AT", wait_ms=500)
            if "OK" in resp:
                already_on = True
                break
            time.sleep_ms(200)

        if already_on:
            logger.info(_TAG, "Modul zaten ACIK, PWR KEY atlanıyor")
        else:
            # Modül kapalı - PWR KEY tetikle
            logger.info(_TAG, "Modul kapali, PWR KEY tetikleniyor...")
            self._pwr_key.value(0)  # Bas
            time.sleep(1.2)
            self._pwr_key.value(1)  # Birak
            logger.info(_TAG, "PWR KEY tetiklendi, modul aciliyor...")

            # Modülün açılmasını bekle
            time.sleep(GPS_BOOT_TIMEOUT_S)

        logger.info(_TAG, "Donanim baslatma tamamlandi")

    def shutdown(self):
        """Modülü güvenli şekilde kapatır."""
        logger.info(_TAG, "Modul kapatiliyor...")
        if self._gps_active:
            self.stop_gps()

        # PWR KEY ile kapat
        if self._pwr_key:
            self._pwr_key.value(0)
            time.sleep(2.0)
            self._pwr_key.value(1)

        # Enable kapat
        if self._en_pin:
            self._en_pin.value(0)

        logger.info(_TAG, "Modul kapatildi")

    # =========================================================================
    # AT KOMUT İLETİŞİMİ
    # =========================================================================

    def send_at(self, cmd, wait_ms=500):
        """AT komutu gönderir ve yanıtı döndürür."""
        if not self._uart:
            logger.error(_TAG, "UART baslatilmamis!")
            return ""

        # Buffer temizle
        while self._uart.any():
            self._uart.read()

        self._uart.write((cmd + "\r\n").encode('utf-8'))

        start = time.ticks_ms()
        response = b""

        while time.ticks_diff(time.ticks_ms(), start) < wait_ms:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    response += chunk
                if b"OK" in response or b"ERROR" in response:
                    break
            time.sleep_ms(10)

        try:
            return response.decode('utf-8', 'ignore').strip()
        except:
            return ""

    def wait_ready(self, timeout_s=30):
        """Modülün hazır olmasını bekler."""
        logger.info(_TAG, "Modul baglantisi bekleniyor...")
        start = time.ticks_ms()

        while time.ticks_diff(time.ticks_ms(), start) < timeout_s * 1000:
            resp = self.send_at("AT", wait_ms=500)
            if "OK" in resp:
                logger.info(_TAG, "Modul HAZIR!")
                return True
            time.sleep(1)

        logger.error(_TAG, "Modul baglanti zaman asimi!")
        return False

    # =========================================================================
    # GPS İŞLEVLERİ
    # =========================================================================

    def start_gps(self):
        """GPS alıcısını başlatır."""
        resp = self.send_at("AT+CGPS=1", wait_ms=1000)
        if "OK" in resp or "already started" in resp.lower():
            self._gps_active = True
            self._first_fix = False
            self._boot_ticks = time.ticks_ms()
            logger.info(_TAG, "GPS baslatildi")
            return True

        logger.error(_TAG, "GPS baslatilamadi: " + resp)
        return False

    def stop_gps(self):
        """GPS alıcısını durdurur."""
        self.send_at("AT+CGPS=0", wait_ms=1000)
        self._gps_active = False
        logger.info(_TAG, "GPS durduruldu")

    def get_gps_data(self):
        """
        GPS verisini alır ve çözümler.
        
        Returns:
            dict veya None: GPS verisi sözlüğü, veri yoksa None
            {
                "lat": float,      # Enlem (ondalık derece)
                "lon": float,      # Boylam (ondalık derece)
                "alt": float,      # Rakım (metre)
                "speed": float,    # Hız (km/h)
                "link": str,       # Google Maps linki
                "first_fix": bool  # İlk konum mu?
            }
        """
        if not self._gps_active:
            return None

        resp = self.send_at("AT+CGPSINFO", wait_ms=500)
        data = self._parse_cgpsinfo(resp)

        if data and not self._first_fix:
            elapsed = time.ticks_diff(time.ticks_ms(), self._boot_ticks) / 1000
            data["first_fix"] = True
            data["fix_time_s"] = round(elapsed, 2)
            self._first_fix = True
            logger.info(_TAG, "ILK KONUM! {:.1f}s sonra".format(elapsed))
        elif data:
            data["first_fix"] = False

        return data

    # =========================================================================
    # NMEA ÇÖZÜMLEME
    # =========================================================================

    @staticmethod
    def _nmea_to_decimal(coord_str, direction):
        """NMEA koordinatını ondalık dereceye çevirir."""
        try:
            if not coord_str:
                return 0.0

            dot_index = coord_str.find('.')
            if dot_index == -1:
                return 0.0

            degrees = float(coord_str[:dot_index - 2])
            minutes = float(coord_str[dot_index - 2:])
            val = degrees + (minutes / 60.0)

            if direction.upper() in ['S', 'W']:
                val = -val

            return round(val, 6)
        except:
            return 0.0

    def _parse_cgpsinfo(self, resp):
        """AT+CGPSINFO yanıtını çözümler."""
        if "+CGPSINFO:" not in resp:
            return None

        try:
            start_idx = resp.find("+CGPSINFO:") + 10
            content = resp[start_idx:].split('\n')[0].strip()
            parts = content.split(',')

            if len(parts) < 8 or parts[0] == '':
                return None

            lat = self._nmea_to_decimal(parts[0], parts[1])
            lon = self._nmea_to_decimal(parts[2], parts[3])

            try:
                alt = float(parts[6]) if parts[6] else 0.0
            except:
                alt = 0.0

            try:
                speed = float(parts[7]) if parts[7] else 0.0
            except:
                speed = 0.0

            return {
                "lat": lat,
                "lon": lon,
                "alt": round(alt, 1),
                "speed": round(speed, 2),
                "link": "https://www.google.com/maps?q={},{}".format(lat, lon)
            }
        except:
            return None

    # =========================================================================
    # DURUM BİLGİSİ
    # =========================================================================

    def get_signal_quality(self):
        """Sinyal kalitesini sorgular (0-31 arası, 31=en iyi)."""
        resp = self.send_at("AT+CSQ", wait_ms=500)
        try:
            if "+CSQ:" in resp:
                val = resp.split("+CSQ:")[1].split(",")[0].strip()
                return int(val)
        except:
            pass
        return -1

    def get_network_info(self):
        """Ağ bilgisini sorgular."""
        return self.send_at("AT+COPS?", wait_ms=1000)

    @property
    def is_gps_active(self):
        return self._gps_active
