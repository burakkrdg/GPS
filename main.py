"""
main.py - Ana Uygulama
========================
Tüm modülleri orkestra eden ana uygulama döngüsü.
Modüler yapıdaki sürücüler ve yöneticiler burada birleştirilir.

Sistem Akışı:
  1. Sürücüler başlatılır (Battery, Buzzer, BNO055, SIM7500E)
  2. Yöneticiler başlatılır (Power, Activity, Alert)
  3. Ana döngü: GPS okuma, aktivite algılama, uyarı kontrolü
  4. Uyku modu desteği (boot butonu ile)
"""
import gc
import time
from utils import logger

_TAG = "MAIN"

# =============================================================================
# SİSTEM BAŞLATMA
# =============================================================================

def init_system():
    """
    Tüm sürücü ve yöneticileri başlatır.
    
    Returns:
        dict: Başlatılan tüm bileşen referansları
    """
    logger.info(_TAG, "=" * 40)
    logger.info(_TAG, "SISTEM BASLATILIYOR...")
    logger.info(_TAG, "=" * 40)

    components = {}

    # --- 1. Buzzer (İlk başlar, diğer modüller sesli geri bildirim verebilsin) ---
    try:
        from drivers.buzzer import Buzzer
        buzzer = Buzzer()
        components["buzzer"] = buzzer
        logger.info(_TAG, "[OK] Buzzer")
    except Exception as e:
        logger.error(_TAG, "[FAIL] Buzzer: {}".format(e))
        components["buzzer"] = None

    # --- 2. Pil Ölçümü ---
    try:
        from drivers.battery import Battery
        battery = Battery()
        status = battery.get_status()
        logger.info(_TAG, "[OK] Pil: {:.2f}V (%{}) [{}]".format(
            status["voltage"], status["percent"], status["level"]))
        components["battery"] = battery
    except Exception as e:
        logger.error(_TAG, "[FAIL] Pil: {}".format(e))
        components["battery"] = None

    # --- 3. Güç Yönetimi (LED ve Boot butonu) ---
    try:
        from managers.power_manager import PowerManager
        power = PowerManager(
            battery_driver=components.get("battery"),
            buzzer_driver=components.get("buzzer")
        )
        power.led_on()  # Power LED yak
        from config import STATE_RUNNING
        power.state = STATE_RUNNING
        power.start_button_thread()  # Buton izleme thread'ini baslat
        logger.info(_TAG, "[OK] Guc Yonetimi (LED ON, Thread ON)")
        components["power"] = power
    except Exception as e:
        logger.error(_TAG, "[FAIL] Guc Yonetimi: {}".format(e))
        components["power"] = None

    # --- 4. BNO055 IMU ---
    try:
        from drivers.bno055 import BNO055
        bno = BNO055()
        if bno.init():
            logger.info(_TAG, "[OK] BNO055 IMU")
            components["bno"] = bno
        else:
            logger.warn(_TAG, "[WARN] BNO055 baslatilamadi, sensorsuz devam")
            components["bno"] = None
    except Exception as e:
        logger.error(_TAG, "[FAIL] BNO055: {}".format(e))
        components["bno"] = None

    # --- 5. Aktivite & Uyari (devre disi - sonra eklenecek) ---
    components["activity"] = None
    components["alert"] = None

    # --- 7. SIM7500E GPS/GSM ---
    try:
        from drivers.sim7500e import SIM7500E
        sim = SIM7500E()
        sim.init_hardware()
        
        if sim.wait_ready(timeout_s=30):
            sim.start_gps()
            logger.info(_TAG, "[OK] SIM7500E GPS")
        else:
            logger.warn(_TAG, "[WARN] SIM7500E yanitlamiyor")
        
        components["sim"] = sim
    except Exception as e:
        logger.error(_TAG, "[FAIL] SIM7500E: {}".format(e))
        components["sim"] = None

    # --- Başlatma Tamamlandı ---
    gc.collect()

    # Açılış sesi
    if components.get("buzzer"):
        components["buzzer"].pattern_boot()

    active = sum(1 for v in components.values() if v is not None)
    total = len(components)
    logger.info(_TAG, "=" * 40)
    logger.info(_TAG, "SISTEM HAZIR ({}/{} bilesen aktif)".format(active, total))
    logger.info(_TAG, "Bos RAM: {} KB".format(gc.mem_free() // 1024))
    logger.info(_TAG, "=" * 40)

    return components


# =============================================================================
# MODÜL KAPATMA
# =============================================================================

def shutdown_modules(components):
    """Tüm modülleri güvenli şekilde kapatır (uyku öncesi)."""
    logger.info(_TAG, "Moduller kapatiliyor...")

    # GPS/GSM kapat
    sim = components.get("sim")
    if sim:
        try:
            sim.shutdown()
        except:
            pass

    # IMU uyku moduna al
    bno = components.get("bno")
    if bno:
        try:
            bno.shutdown()
        except:
            pass

    # Uyarıları kapat
    alert = components.get("alert")
    if alert:
        alert.disable_alerts()

    # Buzzer kapat
    buzzer = components.get("buzzer")
    if buzzer:
        buzzer.off()

    gc.collect()
    logger.info(_TAG, "Tum moduller kapatildi")


def shutdown_all(components):
    """Tamamen kapatma (Ctrl+C veya kritik hata). Thread dahil."""
    # Buton thread'ini durdur
    power = components.get("power")
    if power:
        try:
            power.stop_button_thread()
        except:
            pass

    shutdown_modules(components)


# =============================================================================
# YENİDEN BAŞLATMA (Uyku sonrası)
# =============================================================================

def wakeup_modules(components):
    """Uyku modundan uyanınca modülleri tekrar başlatır."""
    logger.info(_TAG, "Moduller yeniden baslatiliyor...")

    # Power LED yak
    power = components.get("power")
    if power:
        power.led_on()

    # BNO055 tekrar başlat
    bno = components.get("bno")
    if bno:
        bno.init()

    # Aktivite yöneticisi zaten BNO referansını tutar

    # Uyarıları aktifle
    alert = components.get("alert")
    if alert:
        alert.enable_alerts()

    # SIM7500E tekrar başlat
    sim = components.get("sim")
    if sim:
        sim.init_hardware()
        if sim.wait_ready(timeout_s=30):
            sim.start_gps()

    # Açılış sesi
    buzzer = components.get("buzzer")
    if buzzer:
        buzzer.pattern_boot()

    gc.collect()
    logger.info(_TAG, "Moduller yeniden baslatildi")


# =============================================================================
# ANA DÖNGÜ
# =============================================================================

def main_loop(components):
    """
    Sistem ana döngüsü.
    GPS verisi okuma, aktivite algılama, uyarı kontrolü ve güç yönetimi.
    """
    from config import GPS_POLL_INTERVAL_S

    sim      = components.get("sim")
    battery  = components.get("battery")
    buzzer   = components.get("buzzer")
    power    = components.get("power")

    gps_timer = time.ticks_ms()
    battery_timer = time.ticks_ms()
    status_timer = time.ticks_ms()

    logger.info(_TAG, "Ana dongu baslatildi")

    while True:
        now = time.ticks_ms()

        # -----------------------------------------------------------------
        # 1. UYKU MODU KONTROLÜ (Boot butonu)
        # -----------------------------------------------------------------
        if power and power.check_sleep_request():
            logger.info(_TAG, "Uyku moduna geciliyor...")

            power.enter_sleep(
                shutdown_callback=lambda: shutdown_modules(components)
            )

            # Uyanma sonrası
            logger.info(_TAG, "Uyanma sonrasi yeniden baslat...")
            wakeup_modules(components)
            gps_timer = time.ticks_ms()
            battery_timer = time.ticks_ms()
            continue

        # -----------------------------------------------------------------
        # 2. (Aktivite & Uyari - sonra eklenecek)
        # -----------------------------------------------------------------

        # -----------------------------------------------------------------
        # 4. GPS VERİ OKUMA (Her N saniyede)
        # -----------------------------------------------------------------
        if sim and time.ticks_diff(now, gps_timer) >= GPS_POLL_INTERVAL_S * 1000:
            gps_timer = now

            data = sim.get_gps_data()
            if data:
                # İlk GPS fix sesi
                if data.get("first_fix"):
                    logger.info(_TAG, "ILK GPS FIX! ({:.1f}s)".format(
                        data.get("fix_time_s", 0)))
                    if buzzer:
                        buzzer.pattern_gps_fix()

                # GPS verisi yazdır
                print("\n" + "=" * 44)
                print("  ENLEM  : {}".format(data["lat"]))
                print("  BOYLAM : {}".format(data["lon"]))
                print("  HIZ    : {} km/h".format(data["speed"]))
                print("  RAKIM  : {} m".format(data["alt"]))
                print("  HARITA : {}".format(data["link"]))
                print("=" * 44)
            else:
                print(".", end="")

        # -----------------------------------------------------------------
        # 5. PİL KONTROLÜ (Her 30 saniyede)
        # -----------------------------------------------------------------
        if battery and time.ticks_diff(now, battery_timer) >= 30000:
            battery_timer = now

            if power:
                level = power.check_battery()
                if level == "CRITICAL":
                    logger.error(_TAG, "KRITIK PIL! Sistem kapatilacak...")
                    shutdown_modules(components)
                    if power:
                        power.led_blink(count=10, on_ms=100, off_ms=100)
                        power.led_off()
                    # Deep sleep (uyanmayacak)
                    from machine import deepsleep
                    deepsleep()

        # -----------------------------------------------------------------
        # 6. DURUM RAPORU (Her 60 saniyede)
        # -----------------------------------------------------------------
        if time.ticks_diff(now, status_timer) >= 60000:
            status_timer = now
            gc.collect()

            report = "[DURUM] RAM:{}KB".format(gc.mem_free() // 1024)

            if battery:
                report += " | Pil:{:.1f}V".format(battery.voltage)
            if sim and sim.is_gps_active:
                report += " | GPS:ON"

            logger.info(_TAG, report)

        # -----------------------------------------------------------------
        # Döngü bekleme (CPU yükünü azaltma)
        # -----------------------------------------------------------------
        time.sleep_ms(50)


# =============================================================================
# GİRİŞ NOKTASI
# =============================================================================

def main():
    """Uygulama giriş noktası."""
    components = {}
    try:
        components = init_system()
        main_loop(components)
    except KeyboardInterrupt:
        logger.info(_TAG, "Kullanici tarafindan durduruldu (Ctrl+C)")
    except Exception as e:
        logger.error(_TAG, "KRITIK HATA: {}".format(e))
        import sys
        sys.print_exception(e)
    finally:
        logger.info(_TAG, "Sistem kapatiliyor...")
        try:
            shutdown_all(components)
        except:
            pass


# MicroPython otomatik çalıştırma
main()
