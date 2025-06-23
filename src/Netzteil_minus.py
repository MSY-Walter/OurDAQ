# -*- coding: utf-8 -*-
import spidev
import time
import RPi.GPIO as GPIO

CS_PIN = 22

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

GPIO.setmode(GPIO.BCM)
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)

def write_dac(value):
    
    assert 0 <= value <= 4095
    
    control = 0
    control |= 1 << 15 # Channel A=0 oder B=1
    control |= 1 << 14
    control |= 0 << 13 # Gain 0=2x
    control |= 1 << 12
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    print(f"Sende SPI: {data:016b} (0x{high_byte:02X} {low_byte:02X})")
    
    GPIO.output(CS_PIN, GPIO.LOW)
    spi.xfer2([high_byte, low_byte])
    GPIO.output(CS_PIN, GPIO.HIGH)


def main():
    time.sleep(1)
    #write_dac(0)
    write_dac(4095)

if __name__ == '__main__':
    main()
