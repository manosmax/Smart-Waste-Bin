try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except Exception:
    GPIO = None
    _GPIO_AVAILABLE = False

class PirSampler:
    def __init__(self, pin: int, callback, debounce_ms: int = 300):
        self.pin = pin
        self._stub = not _GPIO_AVAILABLE
        if not self._stub:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            # Callback μόνο σε RISING edge, με debounce 300ms
            GPIO.add_event_detect(
                pin,
                GPIO.RISING,
                callback=callback,
                bouncetime=debounce_ms
            )

    def cleanup(self):
        if not self._stub:
            GPIO.remove_event_detect(self.pin)
            GPIO.cleanup(self.pin)