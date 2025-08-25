# tools/test_footswitch_raw.py
import time
import RPi.GPIO as GPIO

PIN = 17  # BCM numbering

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # enable internal pull-up

def cb(_):
    lvl = GPIO.input(PIN)
    print(f"EDGE: {'HIGH(1, open)' if lvl else 'LOW(0, grounded)'}")

GPIO.add_event_detect(PIN, GPIO.BOTH, callback=cb, bouncetime=25)

print("Reading GPIO17 with pull-up. Press the footswitch or short pin 11 to GND. Ctrl+C to exit.\n")
try:
    while True:
        lvl = GPIO.input(PIN)
        print(f"LEVEL: {'HIGH(1, open)' if lvl else 'LOW(0, grounded)'}")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup(PIN)
