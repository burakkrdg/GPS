from machine import UART, Pin
import time

# --- AYARLAR ---
UART_BAUD = 115200
TX_PIN = 17
RX_PIN = 18

# --- FONKSİYONLAR ---

def init_sim7600_hardware():
    print("--- DONANIM BASLATILIYOR ---")
    # 1. Voltaj Regülatörünü Aç
    en = Pin(12, Pin.OUT)
    en.value(1) 
    time.sleep(0.5)

    # 2. Modülü Ateşle
    sim_key = Pin(10, Pin.OUT)
    sim_key.value(1)
    time.sleep(0.1)

    sim_key.value(0) # Bas
    time.sleep(1.2)
    sim_key.value(1) # Bırak

    print(">> Power Key tetiklendi. Modulun acilmasi bekleniyor...")
    time.sleep(5) 

def send_at(uart, cmd, wait_ms=300):
    # Buffer temizle
    while uart.any():
        uart.read()
    
    uart.write((cmd + "\r\n").encode('utf-8'))
    
    # Cevap bekleme mantığı
    start = time.ticks_ms()
    response = b""
    
    while time.ticks_diff(time.ticks_ms(), start) < wait_ms:
        if uart.any():
            response += uart.read()
            if b"OK" in response or b"ERROR" in response:
                break
                
    try:
        # Hatalı karakterleri göz ardı ederek decode et, çökmesini önler
        return response.decode('utf-8', 'ignore').strip()
    except Exception as e:
        return ""

def wait_for_module_ready(uart):
    print(">> Baglanti kontrol ediliyor (AT)...")
    while True:
        response = send_at(uart, "AT", wait_ms=500)
        if "OK" in response:
            print(">> MODUL HAZIR!")
            return True
        time.sleep(1)

def nmea_to_decimal(coord_str, direction):
    try:
        if not coord_str: return 0.0
        dot_index = coord_str.find('.')
        if dot_index == -1: return 0.0
        
        # Derece ve dakika kısımlarını ayır
        degrees = float(coord_str[:dot_index-2])
        minutes = float(coord_str[dot_index-2:])
        val = degrees + (minutes / 60.0)
        
        # Güney (S) ve Batı (W) yarımküreler için değeri negatif yap
        if direction.upper() in ['S', 'W']: val = -val
        
        # Daha temiz ve hassas değer döndür (Virgülden sonra 6 basamak)
        return round(val, 6)
    except:
        return 0.0

def parse_gps(resp):
    if "+CGPSINFO:" in resp:
        try:
            start_idx = resp.find("+CGPSINFO:") + 10
            content = resp[start_idx:].split('\n')[0].strip()
            parts = content.split(',')
            
            # Veri eksikse veya henüz konum alınamadıysa (,,,,, formatında döner)
            if len(parts) < 8 or parts[0] == '': 
                return None
            
            lat = nmea_to_decimal(parts[0], parts[1])
            lon = nmea_to_decimal(parts[2], parts[3])
            
            # String verileri güvenli bir şekilde sayıya çevir
            try:
                alt = float(parts[6]) if parts[6] else 0.0
            except:
                alt = 0.0
                
            try:
                # Modül genellikle knots cinsinden hız verebilir (modeline göre değişir).
                # NMEA formatında hız knot cinsindedir (1 knot = 1.852 km/h).
                # Ancak SIM7600 CGPSINFO hızı doğrudan km/s cinsinden veriyor olabilir, 
                # manuel test ederek doğrulanabilir. Hızı km/h olarak varsayıyoruz.
                speed = float(parts[7]) if parts[7] else 0.0
            except:
                speed = 0.0
            
            return {
                "lat": lat,
                "lon": lon,
                "link": f"https://www.google.com/maps?q={lat},{lon}",
                "speed": round(speed, 2),
                "alt": round(alt, 1)
            }
        except Exception as e:
            return None
    return None

# --- ANA PROGRAM ---
def main():
    # 1. KRONOMETREYİ BAŞLAT
    boot_time = time.ticks_ms()
    first_fix_received = False 
    
    init_sim7600_hardware()
    
    # UART Tanımlama, RX buffer boyutunu artırarak veri kaybını önleyebiliriz
    sim7600 = UART(2, baudrate=UART_BAUD, tx=TX_PIN, rx=RX_PIN, timeout=1000, rxbuf=512)
    
    wait_for_module_ready(sim7600)
    
    # GPS'i başlat
    send_at(sim7600, "AT+CGPS=1")
    print(">> GPS Verisi Bekleniyor (Her 2 saniyede bir)...")
    
    while True:
        # GPS bilgisini iste
        gps_resp = send_at(sim7600, "AT+CGPSINFO", wait_ms=500)
        data = parse_gps(gps_resp)
        
        if data:
            print("\n" + "=" * 40)
            
            if not first_fix_received:
                total_duration = time.ticks_diff(time.ticks_ms(), boot_time) / 1000
                print(f"!!! İLK KONUM BULUNDU: {total_duration:.2f} SANİYE SONRA !!!")
                print("=" * 40)
                first_fix_received = True 
            
            print(f"ENLEM : {data['lat']} / BOYLAM : {data['lon']}")
            print(f"HIZ   : {data['speed']} km/h")
            print(f"RAKIM : {data['alt']} m")
            print(f"HARITA: {data['link']}")
            print("=" * 40)
        else:
            # Fix alana kadar nokta koyar
            print(".", end="")
            
        time.sleep(2)

if __name__ == "__main__":
    main()
