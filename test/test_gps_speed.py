import machine
import time
from config import SIM_UART_ID, SIM_UART_BAUD, SIM_TX_PIN, SIM_RX_PIN, SIM_PWR_KEY_PIN

"""
SIM7600E GPS Hız (TTFF) Test Aracı
==========================================
Bu kod modülün sadece uydu bulma hızını (HTTP, Sensör vs olmadan) ölçmek içindir.
"""

def send_at(uart, cmd, wait_ms=1000, expected="OK"):
    print("[TX] " + cmd)
    uart.write((cmd + '\r\n').encode())
    start = time.ticks_ms()
    resp = ""
    while time.ticks_diff(time.ticks_ms(), start) < wait_ms:
        if uart.any():
            chunk = uart.read()
            if chunk:
                resp += chunk.decode('utf-8', 'ignore')
                if expected in resp or "ERROR" in resp:
                    break
        time.sleep_ms(10)
    print("[RX] " + resp.strip().replace('\r\n', '  '))
    return resp

def main():
    print("="*40)
    print("  SIM7600E GPS HIZ TESTI BASLIYOR")
    print("="*40)
    
    # 0. Donanım PIN Tetiklemesi (PWR KEY)
    print("\n--- DONANIM GUCU KONTROL EDILIYOR ---")
    pwr_key = machine.Pin(SIM_PWR_KEY_PIN, machine.Pin.OUT)
    pwr_key.value(1)
    
    uart = machine.UART(SIM_UART_ID, baudrate=SIM_UART_BAUD, tx=SIM_TX_PIN, rx=SIM_RX_PIN)
    
    # Modül açık mı kontrol et
    alive = False
    for i in range(3):
        if "OK" in send_at(uart, "AT", wait_ms=500):
            alive = True
            break
            
    if not alive:
        print("[BILGI] Modul KAPALI. PWR_KEY tetikleniyor...")
        pwr_key.value(0)
        time.sleep(1.2)
        pwr_key.value(1)
        print("[BILGI] Modul uyaniyor. Lutfen bekleyin (yaklasik 15s)...")
        
        # Modülün kendine gelmesini bekle
        start_w = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_w) < 25000:
            if "OK" in send_at(uart, "AT", wait_ms=500):
                print("[OK] Modul simdi HAZIR!")
                break
            time.sleep(1)
    else:
        print("[OK] Modul zaten ACIK!")
    
    # 1.5. A-GPS (SUPL) ICIN INTERNET (GPRS) BAGLANTISI ZORUNLUDUR!
    print("\n--- GPRS BAGLANTISI ACILIYOR (A-GPS ICIN) ---")
    send_at(uart, 'AT+CGDCONT=1,"IP","internet"', wait_ms=1000)
    send_at(uart, "AT+CGACT=1,1", wait_ms=3000)
    
    # 2. GPS açıksa kapat (Soğuk başlangıç simülasyonu için kapatıp açmak önemli)
    print("\n--- GPS SIFIRLANIYOR ---")
    send_at(uart, "AT+CGPS=0", wait_ms=1000)
    
    # 3. SUPL Sunucusunu Belirle (A-GPS Destekli)
    print("\n--- A-GPS (SUPL) AYARLANIYOR ---")
    send_at(uart, 'AT+CGPSSUPL="supl.google.com:7275"', wait_ms=500)
    
    # 4. GPS Başlat (MS-Based A-GPS Modu: 1,2)
    print("\n--- GPS BASLATILIYOR ---")
    resp = send_at(uart, "AT+CGPS=1,2", wait_ms=1000)
    if "ERROR" in resp:
        print("A-GPS Desteklenmiyor, Normal GPS deneniyor...")
        send_at(uart, "AT+CGPS=1,1", wait_ms=1000)
        
    start_time = time.ticks_ms()
    print("\n[BILGI] Uydular araniyor. Lutfen bekleyin...")
    
    # 5. Konumu bekle
    fix_found = False
    dots = 0
    
    while not fix_found:
        resp = send_at(uart, "AT+CGPSINFO", wait_ms=500)
        
        if "+CGPSINFO: " in resp:
            # Örnek boş: +CGPSINFO: ,,,,,,,,
            # Örnek dolu: +CGPSINFO: 4048.868,N,02926.802,E,...
            data_str = resp.split("+CGPSINFO: ")[1].split("\n")[0].strip()
            if len(data_str) > 10 and data_str[0] != ',':
                fix_found = True
                end_time = time.ticks_ms()
                ttff = time.ticks_diff(end_time, start_time) / 1000.0
                
                print("\n========================================")
                print(" 🎉 KONUM BULUNDU! (FIX OK)")
                print(" ⏱️ Sure: {:.1f} Saniye".format(ttff))
                print(" 📍 Ham Veri: " + data_str)
                print("========================================\n")
                break
                
        time.sleep(1) # saniyede 1 kez sor


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest iptal edildi.")
