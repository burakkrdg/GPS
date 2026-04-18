import requests
import time
import json
import uuid
import random

API_URL = "https://api.geolifespirit.com/v2/telemetry/ingest"
DEVICE_ID = "1020BA0D337C"
DEVICE_KEY = "BL6Z9QTXIcM-JgrUJElnDBSEsbxa3FAL0Vjh4Nwp2Eg"

HEADERS = {
    "Content-Type": "application/json",
    "X-Device-Id": DEVICE_ID,
    "X-Device-Key": DEVICE_KEY,
    "Connection": "keep-alive"
}

# Başlangıç konumu (Örnek: Kartal / İstanbul civarı)
base_lat = 40.814500
base_lon = 29.446700

def generate_payload():
    """Gerçekçi bir test telemetri nesnesi oluşturur."""
    global base_lat, base_lon

    # Konumu çok ufak hareket ettir
    base_lat += random.uniform(-0.0001, 0.0001)
    base_lon += random.uniform(-0.0001, 0.0001)

    return {
        "eventId": str(uuid.uuid4())[:18], # ESP32'deki gibi kısa UUID
        "batteryPercentage": round(random.uniform(70.0, 75.0), 1),
        "isCharging": False,
        "payload": {
            "location": {
                "latitude": round(base_lat, 6),
                "longitude": round(base_lon, 6),
                "altitude": round(random.uniform(150.0, 170.0), 1),
                "speed": round(random.uniform(0.0, 5.0), 1),
                "direction": random.randint(0, 359),
                "satellites": random.randint(6, 12)
            },
            "activity": {
                "currentState": "resting",
                "totalStepCount": 0,
                "caloriesBurned": 0,
                "walking": {"stepCount": 0, "distanceCovered": 0, "duration": 0, "intensity": 0, "isActive": False},
                "running": {"stepCount": 0, "distanceCovered": 0, "duration": 0, "intensity": 0, "isActive": False},
                "resting": {"duration": 0, "isActive": True, "lastMovement": None},
                "sleeping": {"duration": 0, "deepSleep": False, "isActive": False, "lastMovement": None}
            },
            "health": {
                "heartRate": 0,
                "respirationRate": 0
            },
            "connectivity": {
                "gpsStatus": True,
                "gpsSignalStrength": 85,
                "simCardStatus": True,
                "simCardSignalStrength": 80,
                "bluetoothStatus": False
            },
            "collarStatus": {
                "isRemoved": False,
                "removedAt": None
            },
            "deviceInfo": {
                "firmwareVersion": "1.0.1",
                "imei": "864309070159645",
                "simIccid": "",
                "operatorName": "Turkcell",
                "phoneNumber": ""
            }
        }
    }

def main():
    print(f"==================================================")
    print(f"  PC TELEMETRİ TEST SCRIPT BAŞLATILIYOR")
    print(f"  Hedef: {API_URL}")
    print(f"  Cihaz: {DEVICE_ID}")
    print(f"==================================================\n")

    # Session kullanarak Keep-Alive performansını Caddy üzerinde test ediyoruz
    session = requests.Session()
    session.headers.update(HEADERS)

    count = 1
    while True:
        payload = generate_payload()
        print(f"[{time.strftime('%H:%M:%S')}] Paket #{count} hazirlandi. Gonderiliyor...")
        
        start_time = time.time()
        try:
            # POST isteğini gönder
            response = session.post(API_URL, json=payload, timeout=10)
            elapsed = time.time() - start_time
            
            if response.status_code in (200, 201):
                print(f"  ✅ BASARILI! (HTTP {response.status_code}) | Sure: {elapsed:.3f} sn")
                print(f"  Yanit: {response.text}")
                print(f"  Konum: https://www.google.com/maps?q={payload['payload']['location']['latitude']},{payload['payload']['location']['longitude']}")
            else:
                print(f"  ❌ HATA! (HTTP {response.status_code}) | Sure: {elapsed:.3f} sn")
                print(f"  Yanit: {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️ BAGLANTI HATASI: {e}")

        print("-" * 50)
        
        # 5 saniyede bir gönder (Caddy timeout'unu test etmek için değiştirebilirsiniz)
        count += 1
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest sonlandirildi.")
