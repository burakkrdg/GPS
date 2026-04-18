"""
utils/logger.py - Loglama Sistemi
==================================
Seviyeye göre filtrelenebilen merkezi loglama modülü.
Tüm modüller bu sistemi kullanarak tutarlı log çıktısı üretir.
"""
import time

try:
    from config import LOG_LEVEL, LOG_TO_FILE, LOG_FILE_PATH
except ImportError:
    LOG_LEVEL = 1
    LOG_TO_FILE = False
    LOG_FILE_PATH = "/sd/system.log"

# Log seviyeleri
_LEVELS = {0: "DEBUG", 1: "INFO", 2: "WARN", 3: "ERROR"}
_COLORS = {0: "\033[36m", 1: "\033[32m", 2: "\033[33m", 3: "\033[31m"}
_RESET  = "\033[0m"


def _timestamp():
    """Basit zaman damgası üretir."""
    t = time.localtime()
    return "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])


def _log(level, module, message):
    """Dahili loglama fonksiyonu."""
    if level < LOG_LEVEL:
        return

    level_name = _LEVELS.get(level, "???")
    color = _COLORS.get(level, "")
    ts = _timestamp()

    formatted = "[{}] {}{}{} [{}] {}".format(ts, color, level_name, _RESET, module, message)
    print(formatted)

    if LOG_TO_FILE:
        try:
            with open(LOG_FILE_PATH, "a") as f:
                plain = "[{}] {} [{}] {}\n".format(ts, level_name, module, message)
                f.write(plain)
        except:
            pass


def debug(module, message):
    """Debug seviyesi log."""
    _log(0, module, message)


def info(module, message):
    """Bilgi seviyesi log."""
    _log(1, module, message)


def warn(module, message):
    """Uyarı seviyesi log."""
    _log(2, module, message)


def error(module, message):
    """Hata seviyesi log."""
    _log(3, module, message)
