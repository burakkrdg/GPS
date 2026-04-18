"""
deploy.py - ESP32'ye Dosya Yükleme Scripti
============================================
Proje dosyalarını mpremote ile ESP32'ye yükler.
Kullanım: python deploy.py [port]

Örnek:
  python deploy.py                                 # Otomatik port
  python deploy.py /dev/cu.usbmodem14201           # Manuel port
"""
import subprocess
import sys
import os
import time

# =============================================================================
# YÜKLENECEK DOSYALAR
# =============================================================================

DIRECTORIES = ["utils", "drivers", "managers"]

FILES = [
    "config.py",
    "utils/__init__.py",
    "utils/logger.py",
    "drivers/__init__.py",
    "drivers/sim7500e.py",
    "drivers/bno055.py",
    "drivers/buzzer.py",
    "drivers/battery.py",
    "managers/__init__.py",
    "managers/power_manager.py",
    "managers/activity_manager.py",
    "managers/alert_manager.py",
    "boot.py",
    "main.py",
]

# Renkler
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"


def mpremote(args, port=None, timeout=30):
    """mpremote komutu çalıştırır."""
    cmd = ["mpremote"]
    if port:
        cmd += ["connect", port]
    # Soft-reset'i atla (main.py çalışmasın, raw REPL'e girelim)
    cmd += ["resume"]
    cmd += args
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout"
    except Exception as e:
        return False, "", str(e)


def find_device(port=None):
    """Cihaz bağlantısını test eder."""
    print(f"\n{C}🔍 Cihaz aranıyor...{X}")

    ok, out, err = mpremote(["eval", "import sys; print(sys.platform)"], port)
    if ok and "esp32" in out.lower():
        print(f"{G}✅ Cihaz bulundu: {out.strip()}{X}")
        return True

    # İkinci deneme - reset sonrası
    print(f"  {Y}İlk deneme başarısız, tekrar deneniyor...{X}")
    time.sleep(2)
    ok, out, err = mpremote(["eval", "print('PING')"], port)
    if ok:
        print(f"{G}✅ Cihaz bulundu{X}")
        return True

    print(f"{R}❌ Cihaz bulunamadı!{X}")
    if err:
        # Sadece son satırı göster
        last_line = [l for l in err.strip().split("\n") if l.strip()]
        if last_line:
            print(f"{Y}   Hata: {last_line[-1]}{X}")
    print(f"{Y}   - Seri monitörü kapatın (Thonny vb.){X}")
    print(f"{Y}   - ESP32'nin RESET butonuna basın{X}")
    print(f"{Y}   - Port: python deploy.py /dev/cu.usbmodem14201{X}")
    return False


def create_dirs(port):
    """ESP32'de klasörleri oluşturur."""
    print(f"\n{C}📁 Klasörler oluşturuluyor...{X}")
    for d in DIRECTORIES:
        code = "import os\ntry:\n os.mkdir('{}')\n print('NEW')\nexcept:\n print('OK')".format(d)
        ok, out, _ = mpremote(["exec", code], port)
        st = "oluşturuldu" if "NEW" in out else "zaten var"
        print(f"  📁 /{d}/ - {st}")


def upload(local, remote, port):
    """Dosya yükler."""
    ok, _, err = mpremote(["cp", local, ":{}".format(remote)], port, timeout=30)
    return ok


def deploy(port):
    project = os.path.dirname(os.path.abspath(__file__))

    print(f"\n{B}{'=' * 50}")
    print(f"  🚀 GPS TAKİP SİSTEMİ - ESP32 DEPLOY")
    print(f"{'=' * 50}{X}")

    if not find_device(port):
        sys.exit(1)

    # Dosya kontrolü
    print(f"\n{C}📋 Dosyalar kontrol ediliyor...{X}")
    missing = [f for f in FILES if not os.path.exists(os.path.join(project, f))]
    if missing:
        for f in missing:
            print(f"  {R}❌ {f}{X}")
        sys.exit(1)
    print(f"  {G}✅ {len(FILES)} dosya hazır{X}")

    # Klasörler
    create_dirs(port)

    # Dosya yükleme
    print(f"\n{C}📤 Dosyalar yükleniyor...{X}")
    ok_n, fail_n, total = 0, 0, len(FILES)

    for i, fp in enumerate(FILES, 1):
        local = os.path.join(project, fp)
        sz = os.path.getsize(local)
        sz_s = f"{sz}B" if sz < 1024 else f"{sz/1024:.1f}KB"
        bar = "█" * int(i/total*20) + "░" * (20 - int(i/total*20))

        print(f"  [{bar}] ({i}/{total}) {fp} ({sz_s}) ... ", end="", flush=True)

        if upload(local, fp, port):
            print(f"{G}✅{X}")
            ok_n += 1
        else:
            print(f"{R}❌{X}")
            fail_n += 1
            # Hata sonrası kısa bekle
            time.sleep(1)

    # Rapor
    print(f"\n{B}{'=' * 50}{X}")
    if fail_n == 0:
        print(f"{G}{B}  ✅ YÜKLEME TAMAMLANDI! ({ok_n}/{total}){X}")
        print(f"\n{Y}  🔄 Cihazı resetlemek ister misiniz? (E/h): {X}", end="")
        try:
            if input().strip().lower() in ["e", "evet", "y", "yes", ""]:
                print(f"  {C}Resetleniyor...{X}")
                mpremote(["reset"], port)
                print(f"  {G}✅ Sistem başlıyor!{X}")
        except EOFError:
            pass
    else:
        print(f"{R}{B}  ⚠️  {ok_n} başarılı, {fail_n} başarısız{X}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else None
    deploy(port)
