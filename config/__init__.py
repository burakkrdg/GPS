"""
config.py - Sistem Konfigürasyon Dosyası
=========================================
Tüm pin tanımları, sabitler ve sistem parametreleri burada merkezi olarak tutulur.
Donanım değişikliklerinde sadece bu dosya güncellenir.
"""

# =============================================================================
# PIN TANIMLARI
# =============================================================================

# --- SIM7500E Modülü ---
SIM_UART_ID      = 2
SIM_UART_BAUD    = 115200
SIM_TX_PIN       = 17
SIM_RX_PIN       = 18
SIM_PWR_KEY_PIN  = 10       # Modül Power Key
SIM_EN_PIN       = 12       # Modül Enable (Voltaj Regülatörü)
SIM_UART_RXBUF   = 1024     # RX buffer boyutu

# --- BNO055 IMU Sensörü ---
BNO_SDA_PIN      = 36
BNO_SCL_PIN      = 37
BNO_I2C_ID       = 0
BNO_I2C_FREQ     = 400000
BNO_ADDRESS      = 0x28

# --- Buzzer ---
BUZZER_PIN       = 7

# --- Pil Ölçümü ---
BATTERY_ADC_PIN  = 1
# Voltaj bölücü dirençler (ohm)
# Devre: VBAT ---[R1]--- ADC_PIN ---[R2]--- GND
BATTERY_R1       = 120000   # Üst direnç - VBAT tarafı (120K)
BATTERY_R2       = 220000   # Alt direnç - GND tarafı (220K)
# ADC referans voltajı (ESP32 dahili)
ADC_VREF         = 3.3
ADC_RESOLUTION   = 4095     # 12-bit ADC

# --- Power LED ---
POWER_LED_PIN    = 13

# --- Touch Pin (Çarpışma Algılama) ---
TOUCH_PIN        = 9        # Touch - GPIO9

# =============================================================================
# SİSTEM PARAMETRELERİ
# =============================================================================

# --- GPS Ayarları ---
GPS_POLL_INTERVAL_S   = 2       # GPS veri alma aralığı (saniye)
GPS_BOOT_TIMEOUT_S    = 10      # Modül açılış bekleme süresi

# --- Aktivite Algılama ---
ACTIVITY_POLL_MS      = 200     # IMU okuma aralığı (ms)
ACCEL_WALK_THRESHOLD  = 1.2     # Yürüme ivme eşiği (g)
ACCEL_RUN_THRESHOLD   = 2.5     # Koşma ivme eşiği (g)
ACCEL_IDLE_THRESHOLD  = 0.3     # Hareketsizlik eşiği (g)
ACTIVITY_WINDOW_SIZE  = 10      # Kaç örnek üzerinden ortalama alınacak

# --- Kaybolma Algılama ---
LOST_TIMEOUT_S        = 300     # Hareketsizlik süre eşiği (5 dakika)
LOST_BUZZ_INTERVAL_S  = 5       # Kaybolma buzzer çalma aralığı

# --- Çarpışma / Darbe Algılama ---
TOUCH_THRESHOLD       = 50000     # Touch pini eşik değeri (test_touch.py ile kalibre et!)
IMPACT_ACCEL_G        = 4.0     # Darbe ivme eşiği (g)

# --- Pil Seviyeleri ---
BATTERY_FULL_V        = 4.2     # Tam dolu voltaj
BATTERY_LOW_V         = 3.3     # Düşük pil uyarı voltajı
BATTERY_CRITICAL_V    = 3.0     # Kritik pil voltajı (kapatma)

# --- Uyku Modu ---
SLEEP_DEBOUNCE_MS     = 500     # Buton debounce süresi

# --- Loglama ---
LOG_LEVEL             = 1       # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR
LOG_TO_FILE           = False   # Dosyaya log yazma (SD kart için)
LOG_FILE_PATH         = "/sd/system.log"

# =============================================================================
# SİSTEM DURUMLARI
# =============================================================================
STATE_BOOTING     = 0
STATE_RUNNING     = 1
STATE_SLEEPING    = 2
STATE_LOW_BATTERY = 3
STATE_LOST        = 4
STATE_ERROR       = 5
