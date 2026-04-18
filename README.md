# 📍 GPS Takip Sistemi

ESP32-S3 üzerinde MicroPython ile çalışan, gerçek zamanlı GPS takibi, aktivite algılama ve akıllı uyarı sistemi içeren gömülü yazılım projesi.

---

## 🔧 Donanım

| Bileşen | Model | Arayüz |
|---|---|---|
| Mikrodenetleyici | ESP32-S3 | — |
| GPS / GSM Modülü | SIM7500E | UART2 |
| IMU Sensörü | BNO055 | I2C |
| Buzzer | Pasif | GPIO7 |
| Pil Ölçümü | Voltaj Bölücü | ADC1 |
| Power LED | — | GPIO13 |
| Touch Pin | GPIO9 | Kapasitif |

---

## ✨ Özellikler

**GPS & Konum**
- SIM7500E modülü üzerinden gerçek zamanlı konum verisi
- NMEA → Ondalık derece dönüşümü
- Enlem, boylam, rakım, hız bilgisi
- İlk konum alım süresi ölçümü
- Google Maps linki otomatik üretimi

**Aktivite Algılama**
- BNO055 ivmeölçer verisiyle yürüme / koşma / hareketsizlik tespiti
- Kayma penceresi (sliding window) filtresi ile gürültü azaltma
- Yapılandırılabilir eşik değerleri (`config.py`)

**Uyarı Sistemi**
- 🔴 **Kaybolma alarmı**: 5 dakika hareketsizlik sonrası buzzer ile uyarı
- 💥 **Darbe algılama**: 4g üzeri ivmede çarpışma tespiti
- 👆 **Touch uyarısı**: Kapasitif dokunma sensörü ile fiziksel uyarı

**Güç Yönetimi**
- Boot butonu ile uyku / uyanma kontrolü (1.5 sn uzun basma)
- Uyku modunda modüller kapatılır, LED söner
- Pil voltajı izleme: düşük pil uyarısı ve kritik seviyede kapatma
- USB bağlantısı uyku sırasında korunur

---

## 📁 Proje Yapısı

```
GPS/
├── boot.py                  # ESP32 açılış dosyası
├── main.py                  # Ana uygulama döngüsü
├── config.py                # Tüm pin ve parametre tanımları
├── deploy.py                # mpremote ile ESP32'ye yükleme scripti
├── sim7600_gps.py           # Ham GPS test scripti
│
├── drivers/
│   ├── sim7500e.py          # SIM7500E GPS/GSM sürücüsü
│   ├── bno055.py            # BNO055 IMU sürücüsü
│   ├── buzzer.py            # Buzzer sürücüsü ve ses desenleri
│   └── battery.py           # Pil voltaj ölçüm sürücüsü
│
├── managers/
│   ├── activity_manager.py  # Aktivite algılama yöneticisi
│   ├── alert_manager.py     # Uyarı yöneticisi (kaybolma, darbe, touch)
│   └── power_manager.py     # Güç ve uyku yöneticisi
│
├── utils/
│   └── logger.py            # Seviyeli loglama (DEBUG/INFO/WARN/ERROR)
│
└── firmware/
    └── ESP32_GENERIC_S3-20251209-v1.27.0.bin  # MicroPython firmware
```

---

## 🚀 Kurulum

### 1. MicroPython Firmware Yükle

```bash
esptool.py --chip esp32s3 erase_flash
esptool.py --chip esp32s3 write_flash -z 0x0 firmware/ESP32_GENERIC_S3-20251209-v1.27.0.bin
```

### 2. Bağımlılıkları Yükle

```bash
pip install mpremote esptool
```

### 3. Projeyi ESP32'ye Yükle

```bash
python deploy.py                          # Otomatik port algılama
python deploy.py /dev/cu.usbmodem14201   # Manuel port
```

---

## ⚙️ Yapılandırma

Tüm pin tanımları ve sistem parametreleri `config.py` dosyasında merkezi olarak tutulur.

```python
# GPS
GPS_POLL_INTERVAL_S = 2       # Konum alma aralığı (saniye)

# Aktivite eşikleri
ACCEL_WALK_THRESHOLD = 1.2    # Yürüme ivme eşiği (g)
ACCEL_RUN_THRESHOLD  = 2.5    # Koşma ivme eşiği (g)

# Kaybolma tespiti
LOST_TIMEOUT_S = 300          # Hareketsizlik süresi (5 dakika)

# Pil seviyeleri
BATTERY_LOW_V      = 3.3      # Düşük pil uyarısı (V)
BATTERY_CRITICAL_V = 3.0      # Kritik seviye - kapatma (V)
```

---

## 📝 Lisans

MIT
