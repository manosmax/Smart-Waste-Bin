import os
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"   

try:
    from gpiozero import DigitalInputDevice
    _GPIO_AVAILABLE = True
except Exception:
    DigitalInputDevice = None
    _GPIO_AVAILABLE = False


class PirSampler:
    def __init__(self, pin: int):
        self.pin = pin
        self._stub = not _GPIO_AVAILABLE
        if not self._stub:
            self._device = DigitalInputDevice(pin)

    def read(self) -> bool:
        if self._stub:
            return False
        return bool(self._device.value)

    def cleanup(self):
        if not self._stub:
            self._device.close()