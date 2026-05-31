try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except Exception:
    GPIO = None
    _GPIO_AVAILABLE = False

class PirSampler:
    def __init__(self, pin: int):
        self.pin = pin
        self._stub = not _GPIO_AVAILABLE
        if not self._stub:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN,pull_up_down=GPIO.PUD_DOWN)

    def read(self) -> bool:
        if self._stub:
            return False
        return bool(GPIO.input(self.pin))

    def cleanup(self):
        if not self._stub:
            GPIO.cleanup(self.pin)