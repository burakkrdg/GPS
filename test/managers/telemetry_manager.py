"""
managers/telemetry_manager.py - Telemetri Yönetici Modülü
==========================================================
Sensör verilerini JSON payload olarak oluşturur ve
GeoLifeSpirit API'sine HTTP POST ile gönderir.
PostgreSQL veritabanına telemetri kaydı oluşturur.
"""
import time
import gc
from utils import logger
from config import (
    API_BASE_URL, API_INGEST_PATH, API_CONFIG_PATH, DEVICE_ID, DEVICE_KEY,
    TELEMETRY_INTERVAL_S, APN_NAME, FIRMWARE_VERSION
)

_TAG = "TELEMETRY"


class TelemetryManager:
    """Telemetri verisi oluşturma ve API'ye gönderme yöneticisi."""

    def __init__(self, sim_driver, battery_driver=None, activity_manager=None):
        self._sim = sim_driver
        self._battery = battery_driver
        self._activity = activity_manager

        self._gprs_ready = False
        self._last_send = 0
        self._send_count = 0
        self._fail_count = 0
        self._last_gps = None        # Son GPS verisi cache

        # Cihaz bilgileri (bir kez çekilir)
        self._imei = ""
        self._operator = ""

        # Dinamik Konfigürasyon (PDF Referansına göre)
        self._report_interval = TELEMETRY_INTERVAL_S
        self._emergency_enabled = False
        self._emergency_interval = 10
        self._low_battery_threshold = 15
        self._power_save_threshold = 10
        self._config_version = 0
        self._sync_needed = True

        logger.info(_TAG, "Telemetri yoneticisi hazir")

    # =========================================================================
    # BAŞLATMA
    # =========================================================================

    def init(self):
        """GPRS bağlantısını kurar ve cihaz bilgilerini çeker."""
        if not self._sim:
            logger.error(_TAG, "SIM modulu yok, telemetri devre disi")
            return False

        # GPRS kur
        self._gprs_ready = self._sim.setup_gprs(apn=APN_NAME)

        # IMEI çek
        self._fetch_device_info()

        return self._gprs_ready

    def _fetch_device_info(self):
        """Cihaz IMEI ve operatör bilgisini AT ile çeker."""
        try:
            resp = self._sim.send_at("AT+CGSN", wait_ms=1000)
            lines = resp.split("\n")
            for line in lines:
                line = line.strip()
                if line.isdigit() and len(line) >= 14:
                    self._imei = line
                    break

            resp = self._sim.send_at("AT+COPS?", wait_ms=1000)
            if "+COPS:" in resp:
                try:
                    parts = resp.split('"')
                    if len(parts) >= 2:
                        self._operator = parts[1]
                except:
                    pass

            logger.info(_TAG, "IMEI: {} | Operator: {}".format(
                self._imei, self._operator))
        except Exception as e:
            logger.error(_TAG, "Cihaz bilgisi alinamadi: {}".format(e))

    # =========================================================================
    # KONFİGÜRASYON SENKRONİZASYONU
    # =========================================================================

    def sync_config(self):
        """Sunucudan güncel cihaz konfigürasyonunu çeker."""
        if not self._sim: return False

        url = "{}/{}/{}".format(API_BASE_URL, API_CONFIG_PATH, DEVICE_ID)
        logger.info(_TAG, "Sunucu konfigurasyonu cekiliyor...")
        
        status, resp = self._sim.http_get(url)
        if status == 200 and resp:
            try:
                import json
                data = json.loads(resp)
                if data.get("ok") and "config" in data:
                    cfg = data["config"]
                    
                    # Versiyon kontrolü
                    new_version = cfg.get("configVersion", 0)
                    if new_version != self._config_version or self._sync_needed:
                        self._report_interval = cfg.get("reportIntervalSec", TELEMETRY_INTERVAL_S)
                        self._emergency_enabled = cfg.get("emergencyEnabled", False)
                        self._emergency_interval = cfg.get("emergencyIntervalSec", 10)
                        self._low_battery_threshold = cfg.get("lowBatteryThreshold", 15)
                        self._power_save_threshold = cfg.get("powerSaveThreshold", 10)
                        self._config_version = new_version
                        self._sync_needed = False
                        
                        logger.info(_TAG, "[OK] Konfigurasyon guncellendi (v{})".format(new_version))
                        logger.info(_TAG, "Yeni aralik: {}s".format(self._report_interval))
                    return True
            except Exception as e:
                logger.error(_TAG, "Konfig parse hata: {}".format(e))
        else:
            logger.warn(_TAG, "Konfig cekilemedi (HTTP {})".format(status))
        return False

    # =========================================================================
    # PAYLOAD OLUŞTURMA
    # =========================================================================

    def _generate_event_id(self):
        """Basit UUID benzeri ID oluşturur (MicroPython uyumlu)."""
        import urandom
        t = time.time()
        r = urandom.getrandbits(32)
        return "{:08x}-{:04x}-{:04x}".format(
            int(t) & 0xFFFFFFFF,
            (r >> 16) & 0xFFFF,
            r & 0xFFFF
        )

    def build_payload(self, gps_data=None):
        """
        Tüm sensör verilerinden API uyumlu JSON payload oluşturur.

        Args:
            gps_data: GPS verisi dict (lat, lon, alt, speed) veya None

        Returns:
            str: JSON string
        """
        # Pil bilgisi
        bat_percent = 0.0
        if self._battery:
            bat_percent = float(self._battery.percent)

        # GPS bilgisi
        lat = 0.0
        lon = 0.0
        alt = 0.0
        speed = 0.0
        if gps_data:
            lat = gps_data.get("lat", 0.0)
            lon = gps_data.get("lon", 0.0)
            alt = gps_data.get("alt", 0.0)
            speed = gps_data.get("speed", 0.0)
            self._last_gps = gps_data
        elif self._last_gps:
            lat = self._last_gps.get("lat", 0.0)
            lon = self._last_gps.get("lon", 0.0)
            alt = self._last_gps.get("alt", 0.0)
            speed = self._last_gps.get("speed", 0.0)

        # Aktivite bilgisi
        current_state = "resting"
        step_count = 0
        is_walking = False
        is_running = False

        if self._activity:
            act = self._activity.activity
            if act == "WALKING":
                current_state = "walking"
                is_walking = True
            elif act == "RUNNING":
                current_state = "running"
                is_running = True
            elif act == "IDLE":
                current_state = "resting"

        # Sinyal kalitesi
        gps_signal = 0
        sim_signal = 0
        if self._sim:
            sq = self._sim.get_signal_quality()
            if sq > 0:
                sim_signal = min(int((sq / 31.0) * 100), 100)
            gps_signal = 85 if self._sim.is_gps_active else 0

        # Event ID
        event_id = self._generate_event_id()

        # JSON elle oluştur (ujson yok, bellek tasarrufu)
        json = '{' \
            '"eventId":"' + event_id + '",' \
            '"batteryPercentage":' + str(bat_percent) + ',' \
            '"isCharging":false,' \
            '"payload":{' \
                '"location":{' \
                    '"latitude":' + str(lat) + ',' \
                    '"longitude":' + str(lon) + ',' \
                    '"altitude":' + str(alt) + ',' \
                    '"speed":' + str(speed) + ',' \
                    '"direction":0,' \
                    '"satellites":0' \
                '},' \
                '"activity":{' \
                    '"currentState":"' + current_state + '",' \
                    '"totalStepCount":' + str(step_count) + ',' \
                    '"caloriesBurned":0,' \
                    '"walking":{' \
                        '"stepCount":0,' \
                        '"distanceCovered":0,' \
                        '"duration":0,' \
                        '"intensity":0,' \
                        '"isActive":' + ('true' if is_walking else 'false') + \
                    '},' \
                    '"running":{' \
                        '"stepCount":0,' \
                        '"distanceCovered":0,' \
                        '"duration":0,' \
                        '"intensity":0,' \
                        '"isActive":' + ('true' if is_running else 'false') + \
                    '},' \
                    '"resting":{' \
                        '"duration":0,' \
                        '"isActive":' + ('true' if current_state == "resting" else 'false') + ',' \
                        '"lastMovement":null' \
                    '},' \
                    '"sleeping":{' \
                        '"duration":0,' \
                        '"deepSleep":false,' \
                        '"isActive":false,' \
                        '"lastMovement":null' \
                    '}' \
                '},' \
                '"health":{' \
                    '"heartRate":0,' \
                    '"respirationRate":0' \
                '},' \
                '"connectivity":{' \
                    '"gpsStatus":' + ('true' if self._sim and self._sim.is_gps_active else 'false') + ',' \
                    '"gpsSignalStrength":' + str(gps_signal) + ',' \
                    '"simCardStatus":true,' \
                    '"simCardSignalStrength":' + str(sim_signal) + ',' \
                    '"bluetoothStatus":false' \
                '},' \
                '"collarStatus":{' \
                    '"isRemoved":false,' \
                    '"removedAt":null' \
                '},' \
                '"deviceInfo":{' \
                    '"firmwareVersion":"' + FIRMWARE_VERSION + '",' \
                    '"imei":"' + self._imei + '",' \
                    '"simIccid":"",' \
                    '"operatorName":"' + self._operator + '",' \
                    '"phoneNumber":""' \
                '}' \
            '}' \
        '}'

        return json

    # =========================================================================
    # GÖNDERİM
    # =========================================================================

    def send(self, gps_data=None):
        """
        Telemetri verisini oluştur ve API'ye gönder.

        Returns:
            bool: Başarılı mı?
        """
        if not self._sim:
            return False

        # GPRS hazır değilse tekrar dene
        if not self._gprs_ready:
            self._gprs_ready = self._sim.setup_gprs(apn=APN_NAME)
            if not self._gprs_ready:
                logger.error(_TAG, "GPRS baglanti yok, atlaniyor")
                self._fail_count += 1
                return False

        # Payload oluştur
        payload = self.build_payload(gps_data)
        gc.collect()

        logger.info(_TAG, "Payload boyut: {} byte".format(len(payload)))
        print("\n--- TELEMETRI PAYLOAD ---")
        print(payload)
        print("--- / PAYLOAD ---\n")

        # HTTP POST
        url = API_BASE_URL + API_INGEST_PATH
        status, resp = self._sim.http_post(url, payload, device_id=DEVICE_ID, device_key=DEVICE_KEY)

        gc.collect()

        if status in (200, 201):
            self._send_count += 1
            logger.info(_TAG, "[OK] Telemetri #{} gonderildi".format(
                self._send_count))
            return True
        else:
            self._fail_count += 1
            logger.error(_TAG, "[FAIL] Telemetri hata (HTTP {}): {}".format(
                status, resp[:80] if resp else "bos"))
            return False

    # =========================================================================
    # PERİYODİK GÜNCELLEME
    # =========================================================================

    def update(self, gps_data=None):
        """
        Zamanlayıcı ile periyodik telemetri gönderimi ve konfig sync.
        """
        now = time.ticks_ms()

        # Konfigürasyon senkronizasyon zamanı? (Her 5 döngüde bir)
        if self._send_count > 0 and self._send_count % 5 == 0 and not getattr(self, "_config_synced_this_cycle", False):
            self.sync_config()
            self._config_synced_this_cycle = True
        elif self._send_count % 5 != 0:
            self._config_synced_this_cycle = False

        # Gönderim zamanı?
        # reportIntervalSec 0 ise (Premium/Canlı), anında gönder
        interval = self._report_interval
        
        # Pil kontrolü (Düşük pil koruması)
        if self._battery:
            lvl = self._battery.read_percentage()
            if lvl <= self._low_battery_threshold:
                # Aralığı powerSaveThreshold kadar artır
                interval += self._power_save_threshold
                if self._send_count % 10 == 0: # Nadir logla
                    logger.warn(_TAG, "Düsüp pil korumasi: {}s aralik".format(interval))

        if time.ticks_diff(now, self._last_send) >= interval * 1000:
            self._last_send = now
            return self.send(gps_data)

        return None

    # =========================================================================
    # DURUM
    # =========================================================================

    @property
    def send_count(self):
        return self._send_count

    @property
    def fail_count(self):
        return self._fail_count

    @property
    def is_gprs_ready(self):
        return self._gprs_ready
