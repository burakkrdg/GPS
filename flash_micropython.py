"""
flash_micropython.py - ESP32-S3 MicroPython Firmware Yükleme
==============================================================
ESP32-S3'e MicroPython firmware'ini indirir ve yükler.
Kullanım: python flash_micropython.py [port]

Örnek:
  python flash_micropython.py                          # Otomatik port
  python flash_micropython.py /dev/tty.usbmodem14201   # Manuel port
"""
import subprocess
import sys
import os
import glob
import urllib.request
import re
import time

# =============================================================================
# AYARLAR
# =============================================================================
FIRMWARE_URL = "https://micropython.org/download/ESP32_GENERIC_S3/"
FIRMWARE_BASE = "https://micropython.org/resources/firmware/"
FIRMWARE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firmware")
CHIP_TYPE = "esp32s3"

# Renk kodları
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"


def list_ports():
    """Mevcut seri portları listeler."""
    patterns = [
        "/dev/tty.usbmodem*", "/dev/tty.usbserial*",
        "/dev/tty.wchusbserial*", "/dev/tty.SLAB*",
        "/dev/cu.usbmodem*", "/dev/cu.usbserial*",
    ]
    ports = []
    for p in patterns:
        ports.extend(glob.glob(p))
    return sorted(set(ports))


def pick_port(specified=None):
    """Port seçer veya kullanıcıya sorar."""
    if specified:
        print(f"  {C}Belirtilen port: {specified}{X}")
        return specified

    ports = list_ports()
    if not ports:
        print(f"  {R}❌ Hiç seri port bulunamadı!{X}")
        sys.exit(1)
    if len(ports) == 1:
        print(f"  {G}✅ Port: {ports[0]}{X}")
        return ports[0]

    print(f"  {C}Portlar:{X}")
    for i, p in enumerate(ports, 1):
        print(f"    {i}. {p}")
    try:
        c = int(input(f"  {Y}Seçin (1-{len(ports)}): {X}")) - 1
        return ports[c]
    except (ValueError, IndexError):
        sys.exit(1)


def kill_port_users(port):
    """Portu kullanan süreçleri bulur ve kapatma önerir."""
    print(f"\n{C}� Portu kullanan süreçler kontrol ediliyor...{X}")
    
    try:
        result = subprocess.run(
            ["lsof", port], capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            print(f"  {Y}⚠️  Port şu süreçler tarafından kullanılıyor:{X}")
            for line in lines:
                print(f"    {line}")
            
            # PID'leri bul
            pids = set()
            for line in lines[1:]:  # header'ı atla
                parts = line.split()
                if len(parts) >= 2:
                    pids.add(parts[1])
            
            if pids:
                print(f"\n  {Y}Bu süreçleri kapatmak ister misiniz? (E/h): {X}", end="")
                try:
                    ans = input().strip().lower()
                    if ans in ["e", "evet", "y", "yes", ""]:
                        for pid in pids:
                            subprocess.run(["kill", "-9", pid], capture_output=True)
                            print(f"  {G}PID {pid} sonlandırıldı{X}")
                        time.sleep(2)  # Port serbest kalması için bekle
                        return True
                except EOFError:
                    pass
        else:
            print(f"  {G}Port serbest görünüyor{X}")
            return True
    except:
        pass
    
    return True


def download_firmware():
    """MicroPython firmware indirir."""
    print(f"\n{C}📥 Firmware indiriliyor...{X}")
    os.makedirs(FIRMWARE_DIR, exist_ok=True)

    # Mevcut .bin kontrol
    existing = [f for f in os.listdir(FIRMWARE_DIR) if f.endswith(".bin")]
    if existing:
        existing.sort(reverse=True)
        path = os.path.join(FIRMWARE_DIR, existing[0])
        sz = os.path.getsize(path) / (1024 * 1024)
        print(f"  {G}Mevcut firmware: {existing[0]} ({sz:.1f}MB){X}")
        print(f"  {Y}Bunu kullanmak ister misiniz? (E/h): {X}", end="")
        try:
            if input().strip().lower() not in ["h", "n", "hayir", "no"]:
                return path
        except EOFError:
            return path

    # İndir
    firmware_name = None
    try:
        req = urllib.request.Request(FIRMWARE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
        matches = re.findall(r'(ESP32_GENERIC_S3-\d+\.\d+\.\d+\.bin)', html)
        if matches:
            firmware_name = matches[0]
    except:
        pass

    if not firmware_name:
        firmware_name = "ESP32_GENERIC_S3-20251209-v1.27.0.bin"

    url = FIRMWARE_BASE + firmware_name
    path = os.path.join(FIRMWARE_DIR, firmware_name)

    print(f"  {C}İndiriliyor: {firmware_name}{X}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            data, dl = b"", 0
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                data += chunk
                dl += len(chunk)
                if total:
                    pct = dl * 100 // total
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    print(f"\r  [{bar}] {pct}% ({dl//1024}KB)", end="", flush=True)
            print()
        with open(path, "wb") as f:
            f.write(data)
        print(f"  {G}✅ İndirildi ({len(data)/1024/1024:.1f}MB){X}")
        return path
    except Exception as e:
        print(f"  {R}❌ Hata: {e}{X}")
        print(f"  {Y}Manuel: {FIRMWARE_URL} adresinden indirip firmware/ klasörüne koyun{X}")
        sys.exit(1)


def run_esptool(args):
    """esptool çalıştırır (yeni veya eski sürüm uyumlu)."""
    # Önce yeni format dene, sonra eski
    for tool in ["esptool", "esptool.py"]:
        try:
            result = subprocess.run([tool] + args, capture_output=False, text=True, timeout=120)
            return result.returncode == 0
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            print(f"  {R}Zaman aşımı!{X}")
            return False
    
    print(f"  {R}❌ esptool bulunamadı! pip install esptool{X}")
    return False


def main():
    port_arg = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"\n{B}{'=' * 50}")
    print(f"  ⚡ ESP32-S3 MicroPython Firmware Yükleme")
    print(f"{'=' * 50}{X}")

    # 1. Firmware indir/seç
    firmware_path = download_firmware()

    # 2. Port meşgul mü kontrol et
    port = pick_port(port_arg)
    kill_port_users(port)

    # 3. Onay
    print(f"\n{B}{'─' * 50}{X}")
    print(f"  {Y}⚠️  Flash SİLİNECEK ve firmware yüklenecek{X}")
    print(f"  Port:     {port}")
    print(f"  Firmware: {os.path.basename(firmware_path)}")
    print(f"{B}{'─' * 50}{X}")
    print(f"  {Y}Devam? (E/h): {X}", end="")
    try:
        if input().strip().lower() in ["h", "n"]:
            sys.exit(0)
    except EOFError:
        pass

    # 4. Boot moduna alma rehberi
    print(f"\n{B}{Y}📌 ESP32-S3'ü BOOT moduna alın:{X}")
    print(f"   1. BOOT butonuna BASILI TUTUN")
    print(f"   2. RESET butonuna basıp BIRAKIN")
    print(f"   3. BOOT butonunu BIRAKIN")
    print(f"\n   {Y}⚠️  Native USB'de port adı değişebilir!{X}")
    print(f"   {C}Şu anki portlar:{X}")
    for p in list_ports():
        marker = " ← mevcut" if p == port else ""
        print(f"     {p}{marker}")

    print(f"\n   {Y}Boot moduna aldıktan sonra ENTER'a basın...{X}", end="")
    try:
        input()
    except EOFError:
        pass

    # 5. Boot modunda port değişmiş olabilir - tekrar kontrol
    new_ports = list_ports()
    print(f"\n   {C}Boot modundaki portlar:{X}")
    for p in new_ports:
        print(f"     {p}")

    # Yeni port var mı kontrol et
    if port not in new_ports:
        if new_ports:
            if len(new_ports) == 1:
                port = new_ports[0]
                print(f"\n  {G}Port değişti → {port}{X}")
            else:
                print(f"\n  {Y}Port değişmiş gibi görünüyor. Hangi portu kullanayım?{X}")
                for i, p in enumerate(new_ports, 1):
                    print(f"    {i}. {p}")
                try:
                    c = int(input(f"  {Y}Seçin: {X}")) - 1
                    port = new_ports[c]
                except:
                    port = new_ports[0]
        else:
            print(f"  {R}❌ Port kayboldu! Boot moduna girdiğinden emin misin?{X}")
            sys.exit(1)

    # 6. Flash sil
    print(f"\n{C}🗑️  Flash siliniyor ({port})...{X}")
    if not run_esptool(["--chip", CHIP_TYPE, "--port", port, "erase-flash"]):
        # Eski komut formatını dene
        if not run_esptool(["--chip", CHIP_TYPE, "--port", port, "erase_flash"]):
            print(f"  {R}❌ Flash silinemedi{X}")
            sys.exit(1)

    print(f"  {G}✅ Flash silindi{X}")
    time.sleep(2)

    # 7. Firmware yükle
    print(f"\n{C}� Firmware yükleniyor...{X}")
    if not run_esptool([
        "--chip", CHIP_TYPE, "--port", port, "--baud", "460800",
        "write-flash", "-z", "0x0", firmware_path
    ]):
        # Eski komut formatını dene
        if not run_esptool([
            "--chip", CHIP_TYPE, "--port", port, "--baud", "460800",
            "write_flash", "-z", "0x0", firmware_path
        ]):
            print(f"  {R}❌ Firmware yüklenemedi{X}")
            sys.exit(1)

    # 8. Tamamlandı
    print(f"\n{B}{'=' * 50}")
    print(f"  {G}✅ MicroPython başarıyla yüklendi!{X}")
    print(f"\n  {C}Sonraki adımlar:{X}")
    print(f"  1. RESET butonuna basın")
    print(f"  2. Dosyaları yükleyin:")
    print(f"     {B}python deploy.py PORT_ADI{X}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
