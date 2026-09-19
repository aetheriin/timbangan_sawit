import serial

PORT = "COM3"  # sesuaikan setelah cek Device Manager
BAUDRATE = 9600  # coba 9600 dulu, kalau data aneh coba 4800/19200/2400

ser = serial.Serial(PORT, BAUDRATE, timeout=1)
print(f"Mendengarkan {PORT} @ {BAUDRATE} baud... (Ctrl+C untuk stop)")

while True:
    data = ser.readline()
    if data:
        print(f"RAW: {data}")