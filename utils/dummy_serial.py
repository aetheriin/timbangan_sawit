import random
import time

def simulasi_timbang():
    """Generator yang meniru pembacaan timbangan: naik lalu stabil."""
    berat_final = random.randint(8000, 25000)
    berat_sekarang = 0
    langkah = berat_final / 20

    while berat_sekarang < berat_final:
        berat_sekarang += langkah
        yield {"berat": round(berat_sekarang), "stabil": False}
        time.sleep(0.1)

    for _ in range(5):
        yield {"berat": berat_final, "stabil": True}
        time.sleep(0.5)