"""
drivers/sim7600e.py - SIM7600E GPS/GSM Modül Sürücüsü
=======================================================
SIM7600E modülünün donanım kontrolü, AT komut iletişimi ve GPS veri çözümleme
işlevlerini barındırır.
"""
from machine import UART, Pin
import time
from utils import logger
from config import (
    SIM_UART_ID, SIM_UART_BAUD, SIM_TX_PIN, SIM_RX_PIN,
    SIM_PWR_KEY_PIN, SIM_EN_PIN, SIM_UART_RXBUF, GPS_BOOT_TIMEOUT_S
)

_TAG = "SIM7600E"


class SIM7600E:
    """SIM7600E GPS/GSM modül sürücüsü."""

    def __init__(self):
        self._uart = None
        self._en_pin = None
        self._pwr_key = None
        self._gps_active = False
        self._first_fix = False
        self._boot_ticks = 0
        self._ssl_open = False
        self._ssl_configured = False

    def _clear_uart(self):
        """UART tamponunu temizler ve atilan veriyi döndürür."""
        dump = ""
        if self._uart:
            while self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    dump += chunk.decode('utf-8', 'ignore')
        return dump

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

    def enable_agps(self):
        """A-GPS (SUPL) hazırlıklarını yapar (SIM7600E adresleri ROM'dan çeker)."""
        logger.info(_TAG, "A-GPS (SUPL) ayarlaniyor...")
        
        # 1. GPS servisi açıksa kapatılmalı
        self.send_at("AT+CGPS=0", wait_ms=1000)
        
        # Sadece kapalı tutmak SUPL öncesi yetiyor.
        # "AT+CGPSSUPL" SIM7600 ROM'unda çakılı olduğu için göndermiyoruz.
        
        return True

    def start_gps(self):
        """GPS alıcısını başlatır. Zaten çalışıyorsa durumu korur."""
        # 1. Önce zaten açık mı diye kontrol et
        resp = self.send_at("AT+CGPS?", wait_ms=500)
        if "+CGPS: 1" in resp:
            logger.info(_TAG, "GPS zaten calisiyor, acik birakildi")
            self._gps_active = True
            self._first_fix = False
            self._boot_ticks = time.ticks_ms()
            return True

        # 2. Açık değilse A-GPS (MS-Based) başlatmayı dene (1,2)
        resp = self.send_at("AT+CGPS=1,2", wait_ms=1000)
        if "ERROR" in resp:
            # SUPL desteklemiyorsa normal (standalone) baslat
            logger.warn(_TAG, "A-GPS basarisiz, normal GPS (Standalone) deneniyor...")
            resp = self.send_at("AT+CGPS=1,1", wait_ms=1000)
            
        if "OK" in resp or "ERROR" in resp: 
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

        resp = self.send_at("AT+CGPSINFO", wait_ms=200)
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
    # GPRS / HÜCRESEL VERİ
    # =========================================================================

    def setup_gprs(self, apn="internet"):
        """GPRS/PDP bağlantısını kurar."""
        logger.info(_TAG, "GPRS kuruluyor (APN: {})...".format(apn))

        # 1. Önce Hangi Ağa Bağlıyız (2G/3G/4G) Onu Öğrenelim
        cpsi = self.send_at("AT+CPSI?", wait_ms=1000)
        net_tech = "Bilinmiyor"
        if "+CPSI: LTE" in cpsi:
            net_tech = "4G LTE"
        elif "+CPSI: GSM" in cpsi:
            net_tech = "2G GSM"
        elif "+CPSI: WCDMA" in cpsi or "UTRAN" in cpsi:
            net_tech = "3G"
            
        logger.info(_TAG, "Baglanti Teknolojisi: {}".format(net_tech))

        # 2. PDP context ayarla
        self.send_at('AT+CGDCONT=1,"IP","{}"'.format(apn), wait_ms=2000)
        time.sleep(1)

        # 3. PDP context aktifle
        resp = self.send_at("AT+CGACT=1,1", wait_ms=5000)
        if "OK" in resp:
            logger.info(_TAG, "GPRS baglantisi basarili ({})".format(net_tech))
            return True
        elif "already activated" in resp.lower() or "ERROR" in resp:
            # Zaten aktif olabilir, kontrol et
            resp2 = self.send_at("AT+CGACT?", wait_ms=2000)
            if "+CGACT: 1,1" in resp2:
                logger.info(_TAG, "GPRS zaten aktif ({})".format(net_tech))
                return True

        logger.error(_TAG, "GPRS baglanti hatasi: " + resp)
        return False

    def close_gprs(self):
        """GPRS/PDP bağlantısını kapatır."""
        self.send_at("AT+CGACT=0,1", wait_ms=3000)
        logger.info(_TAG, "GPRS kapatildi")

    # =========================================================================
    # HTTP İŞLEVLERİ
    # =========================================================================

    def send_at_raw(self, cmd, wait_ms=1000):
        """AT komutu gönderir, tüm yanıtı ham olarak döndürür (OK/ERROR beklemez)."""
        if not self._uart:
            return ""

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
            time.sleep_ms(10)

        try:
            return response.decode('utf-8', 'ignore').strip()
        except:
            return ""

    def http_get(self, url, device_id="", device_key=""):
        """
        TCP soket + SSL ile HTTP GET gönderir.
        
        Args:
            url: Tam URL (https://host/path)
            device_id: X-Device-Id header
            device_key: X-Device-Key header
            
        Returns:
            tuple: (status_code, response_body)
        """
        # URL'den host ve path çıkar
        clean = url.replace("https://", "").replace("http://", "")
        slash = clean.find("/")
        host = clean[:slash] if slash > 0 else clean
        path = clean[slash:] if slash > 0 else "/"
        port = 443 if url.startswith("https") else 80

        logger.info(_TAG, "TCP GET: {}{}".format(host, path))

        try:
            # 0. UART tamponundaki çöpü al
            dump = self._clear_uart()
            if "+CCH_PEER" in dump or "CLOSED" in dump or "+CCHCLOSE" in dump:
                self._ssl_open = False

            # 1. SSL Bağlantısı yoksa aç (Aynı logic http_post ile)
            if not getattr(self, "_ssl_open", False):
                if not getattr(self, "_ssl_configured", False):
                    self.send_at("AT+CIPCLOSE=0", wait_ms=500)
                    self.send_at('AT+CSSLCFG="sslversion",0,3', wait_ms=500)
                    self.send_at('AT+CSSLCFG="authmode",0,0', wait_ms=500)
                    self.send_at('AT+CSSLCFG="enableSNI",0,1', wait_ms=500)
                    self.send_at("AT+CCHSTOP", wait_ms=500)
                    self.send_at("AT+CCHSTART", wait_ms=1000)
                    self._ssl_configured = True

                self.send_at("AT+CCHCLOSE=0", wait_ms=500)
                self.send_at("AT+CCHSET=0,0", wait_ms=500)
                self._uart.write('AT+CCHOPEN=0,"{}",{},2\r\n'.format(host, port).encode())

                start = time.ticks_ms()
                open_resp = ""
                while time.ticks_diff(time.ticks_ms(), start) < 15000:
                    if self._uart.any():
                        chunk = self._uart.read()
                        if chunk:
                            open_resp += chunk.decode('utf-8', 'ignore')
                            if "+CCHOPEN: 0,0" in open_resp: break
                    time.sleep_ms(100)

                if "+CCHOPEN: 0,0" not in open_resp:
                    return (0, "")
                self._ssl_open = True

            # 2. HTTP isteği oluştur
            req = "GET {} HTTP/1.1\r\n".format(path)
            req += "Host: {}\r\n".format(host)
            if device_id: req += "X-Device-Id: {}\r\n".format(device_id)
            if device_key: req += "X-Device-Key: {}\r\n".format(device_key)
            req += "Connection: keep-alive\r\n\r\n"
            req_bytes = req.encode('utf-8')

            # 3. Gönder
            self._uart.write("AT+CCHSEND=0,{}\r\n".format(len(req_bytes)).encode())
            time.sleep_ms(50)
            
            # > bekle
            t = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t) < 3000:
                if self._uart.any():
                    if b">" in self._uart.read(): break
                time.sleep_ms(10)

            self._uart.write(req_bytes)
            
            # 4. Yanıtı bekle ve oku (http_post ile aynı mantık)
            resp_data = ""
            start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start) < 15000:
                if self._uart.any():
                    chunk = self._uart.read()
                    if chunk: resp_data += chunk.decode('utf-8', 'ignore')
                if "HTTP/1." in resp_data and "\r\n\r\n" in resp_data:
                    time.sleep_ms(50) # Biraz daha bekle body tamamlansın
                    while self._uart.any():
                        resp_data += self._uart.read().decode('utf-8', 'ignore')
                    break
                time.sleep_ms(50)

            # Basit parser
            status_code = 0
            response_body = ""
            if "HTTP/1." in resp_data:
                try:
                    p = resp_data.find("HTTP/1.")
                    status_code = int(resp_data[p+9:p+12])
                    sep = resp_data.find("\r\n\r\n", p)
                    if sep > 0:
                        response_body = resp_data[sep + 4:].strip()
                        # Temizlik
                        for m in ["+CCHRECV", "OK", "CLOSED"]:
                            if m in response_body:
                                response_body = response_body.split(m)[0].strip()
                except: pass

            return (status_code, response_body)
        except:
            self._ssl_open = False
            return (0, "")

    def http_post(self, url, body, device_id="", device_key=""):
        """
        TCP soket + SSL ile HTTP POST gönderir.
        Ham HTTP isteği oluşturarak tüm header'lar üzerinde tam kontrol sağlar.

        Args:
            url: Tam URL (https://host/path)
            body: JSON string
            device_id: X-Device-Id header
            device_key: X-Device-Key header

        Returns:
            tuple: (status_code, response_body) veya (0, "") hata durumunda
        """
        # URL'den host ve path çıkar
        clean = url.replace("https://", "").replace("http://", "")
        slash = clean.find("/")
        host = clean[:slash] if slash > 0 else clean
        path = clean[slash:] if slash > 0 else "/"
        port = 443 if url.startswith("https") else 80

        logger.info(_TAG, "TCP POST: {}{}".format(host, path))

        try:
            # 0. UART tamponundaki çöpü al ve Peer Closed oldu mu kontrol et
            dump = self._clear_uart()
            if "+CCH_PEER" in dump or "CLOSED" in dump or "+CCHCLOSE" in dump:
                logger.warn(_TAG, "Sunucu sessizce baglantiyi kapandi (Keep-alive timeout)")
                self._ssl_open = False

            # 1. SSL Bağlantısı yoksa aç
            if not getattr(self, "_ssl_open", False):
                logger.info(_TAG, "SSL baglantisi kuruluyor (ilk veya kopuk)...")
                
                # Sadece ilk bağlantıda (veya komple çökerse) SSL ayarlarını yapıyoruz
                if not getattr(self, "_ssl_configured", False):
                    logger.info(_TAG, "SSL parametreleri ayarlaniyor...")
                    self.send_at("AT+CIPCLOSE=0", wait_ms=500)
                    time.sleep_ms(100)
                    
                    self.send_at('AT+CSSLCFG="sslversion",0,3', wait_ms=500)    # TLS 1.2
                    self.send_at('AT+CSSLCFG="authmode",0,0', wait_ms=500)      # Sertifika doğrulaması
                    self.send_at('AT+CSSLCFG="enableSNI",0,1', wait_ms=500)     # SNI aktif
                    
                    self.send_at("AT+CCHSTOP", wait_ms=500)
                    time.sleep_ms(100)
                    self.send_at("AT+CCHSTART", wait_ms=1000)                   # SSL servisini devrede tut
                    
                    self._ssl_configured = True
                else:
                    logger.info(_TAG, "Sadece acik kanal kapatiliyor...")

                # Kopuk veya ölü kanalı sıfırla ve kanalı tekrar aç
                self.send_at("AT+CCHCLOSE=0", wait_ms=500)
                self.send_at("AT+CCHSET=0,0", wait_ms=500)
                self._uart.write('AT+CCHOPEN=0,"{}",{},2\r\n'.format(host, port).encode())

                # +CCHOPEN yanıtını bekle (max 15sn)
                start = time.ticks_ms()
                open_resp = ""
                while time.ticks_diff(time.ticks_ms(), start) < 15000:
                    if self._uart.any():
                        chunk = self._uart.read()
                        if chunk:
                            open_resp += chunk.decode('utf-8', 'ignore')
                            if "+CCHOPEN: 0,0" in open_resp:
                                break
                            if "+CCHOPEN: 0," in open_resp and "+CCHOPEN: 0,0" not in open_resp:
                                logger.error(_TAG, "SSL hata: " + open_resp[:80])
                                return (0, "")
                    time.sleep_ms(100)

                if "+CCHOPEN: 0,0" not in open_resp:
                    logger.error(_TAG, "SSL zaman asimi")
                    self.send_at("AT+CCHCLOSE=0", wait_ms=1000)
                    return (0, "")

                self._ssl_open = True
                logger.info(_TAG, "SSL baglanti OK")

            # 5. HTTP isteği oluştur (tüm header'lar dahil)
            body_bytes = body.encode('utf-8')
            req = "POST {} HTTP/1.1\r\n".format(path)
            req += "Host: {}\r\n".format(host)
            req += "Content-Type: application/json\r\n"
            req += "Content-Length: {}\r\n".format(len(body_bytes))
            if device_id:
                req += "X-Device-Id: {}\r\n".format(device_id)
            if device_key:
                req += "X-Device-Key: {}\r\n".format(device_key)
            req += "Connection: keep-alive\r\n"
            req += "Keep-Alive: timeout=120, max=1000\r\n"
            req += "\r\n"
            req_bytes = req.encode('utf-8') + body_bytes

            # 6. CCHSEND ile veri gönder
            self._uart.write("AT+CCHSEND=0,{}\r\n".format(len(req_bytes)).encode())
            time.sleep_ms(50)

            # > prompt bekle
            prompt = ""
            t = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t) < 3000:
                if self._uart.any():
                    d = self._uart.read()
                    if d:
                        prompt += d.decode('utf-8', 'ignore')
                        if ">" in prompt:
                            break
                        if "ERROR" in prompt:
                            break
                time.sleep_ms(10)

            if ">" not in prompt:
                logger.info(_TAG, "Sunucu yuvasi kapandi (Keep-Alive bitti), yenileniyor...")
                self._ssl_open = False
                self.send_at("AT+CCHCLOSE=0", wait_ms=1000)
                if not getattr(self, "_is_retrying", False):
                    self._is_retrying = True
                    res = self.http_post(url, body, device_id, device_key)
                    self._is_retrying = False
                    return res
                self._is_retrying = False
                return (0, "")

            # Veriyi gönder
            self._uart.write(req_bytes)
            logger.info(_TAG, "Veri gonderildi ({} byte)".format(len(req_bytes)))

            # 7. Echo ve Gönderim Onayını bekle (OK)
            start = time.ticks_ms()
            echo_data = ""
            send_ok = False
            while time.ticks_diff(time.ticks_ms(), start) < 15000:
                if self._uart.any():
                    chunk = self._uart.read()
                    if chunk:
                        echo_data += chunk.decode('utf-8', 'ignore')
                        # CCHSEND onayı "OK" döner
                        if "\r\nOK\r\n" in echo_data or "+CCHSEND" in echo_data:
                            send_ok = True
                            logger.info(_TAG, "CCHSEND onay OK")
                            break
                time.sleep_ms(50)

            if not send_ok:
                logger.info(_TAG, "Sunucu yanit vermedi, yenileniyor...")
                self._ssl_open = False
                self.send_at("AT+CCHCLOSE=0", wait_ms=1000)
                if not getattr(self, "_is_retrying", False):
                    self._is_retrying = True
                    res = self.http_post(url, body, device_id, device_key)
                    self._is_retrying = False
                    return res
                self._is_retrying = False
                return (0, "")

            # 8. Sunucudan gelecek HTTP yanıtını bekle
            # Echo'dan artan veri varsa (sunucu hemen yanıt vermişse) onu sakla
            resp_data = ""
            idx = echo_data.find("\r\nOK\r\n")
            if idx >= 0:
                resp_data = echo_data[idx + 6:]
            else:
                idx = echo_data.find("+CCHSEND")
                if idx >= 0:
                    nl = echo_data.find("\n", idx)
                    if nl > 0:
                        resp_data = echo_data[nl + 1:]

            start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start) < 20000:
                if self._uart.any():
                    chunk = self._uart.read()
                    if chunk:
                        resp_data += chunk.decode('utf-8', 'ignore')

                # Kontrol her döngüde yapılmalı, (veri ilk aşamada şıp diye gelmiş olabilir!)
                if "HTTP/1." in resp_data and "\r\n\r\n" in resp_data:
                    # Gecikmeyi tamamen min seviyeye indirip beklemeden çıkıyoruz
                    time.sleep_ms(10)
                    while self._uart.any():
                        extra = self._uart.read()
                        if extra:
                            resp_data += extra.decode('utf-8', 'ignore')
                    break
                time.sleep_ms(10)

            # DEBUG
            print("\n--- RAW YANIT ---")
            print(repr(resp_data[:500]))
            print("--- / RAW ---\n")

            # 10. HTTP yanıtını çözümle
            status_code = 0
            response_body = ""

            if "HTTP/1." in resp_data:
                try:
                    idx = resp_data.find("HTTP/1.")
                    status_line = resp_data[idx:resp_data.find("\r\n", idx)]
                    parts = status_line.split(" ")
                    if len(parts) >= 2:
                        status_code = int(parts[1])
                except:
                    pass

                # Body
                try:
                    sep = resp_data.find("\r\n\r\n", resp_data.find("HTTP/1."))
                    if sep > 0:
                        response_body = resp_data[sep + 4:].strip()
                        # AT komut artıklarını temizle
                        for m in ["+CIPCLOSE", "+CIPSEND", "CLOSED", "\r\nOK", "+CCH_PEER_CLOSED", "+CCHCLOSE"]:
                            idx = response_body.find(m)
                            if idx > 0:
                                response_body = response_body[:idx].strip()
                except:
                    pass

            logger.info(_TAG, "HTTP yanit: {} | {}".format(
                status_code, response_body[:80] if response_body else "bos"))

            self._ssl_open = True # Successful post clears any state
            self._is_retrying = False
            return (status_code, response_body)

        except Exception as e:
            logger.error(_TAG, "TCP POST hata: {}".format(e))
            self._ssl_open = False
            self._is_retrying = False
            try:
                self.send_at("AT+CCHCLOSE=0", wait_ms=1000)
            except:
                pass
            return (0, "")

    # =========================================================================
    # DURUM BİLGİSİ
    # =========================================================================

    def get_signal_quality(self):
        """Sinyal kalitesini sorgular (0-31 arası, 31=en iyi)."""
        resp = self.send_at("AT+CSQ", wait_ms=200)
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
