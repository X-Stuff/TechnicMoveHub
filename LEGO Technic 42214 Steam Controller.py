# INSTALLATION:
# pip install -r requirements.txt

import sys
import asyncio
import time
import keyboard

from bleak import BleakScanner, BleakClient
from steamcontroller import read_steam_controller

start_time = 0

class TechnicMoveHub:
    def __init__(self, device_name):
        self.device_name = device_name
        self.service_uuid = "00001623-1212-EFDE-1623-785FEABCD123"
        self.char_uuid = "00001624-1212-EFDE-1623-785FEABCD123"
        self.client = None

        self.LIGHTS_OFF_OFF =    0b100
        self.LIGHTS_OFF_ON =     0b101
        self.LIGHTS_ON_ON =      0b000

    async def scan_and_connect(self):
        scanner = BleakScanner()
        print(f"searching for Technic Move Hub...")
        devices = await scanner.discover(timeout=5)

        for device in devices:
            if device.name is not None and self.device_name in device.name:
                print(f"Found device: {device.name} with address: {device.address}")
                self.client = BleakClient(device)
                await self.client.connect()
                if self.client.is_connected:
                    print(f"Connected to {self.device_name}")
                    paired = await self.client.pair(protection_level=2)
                    if not paired:
                        print(f"could not pair")
                    return True
                else:
                    print(f"Failed to connect to {self.device_name}")
        print(f"Device {self.device_name} not found.")
        return False

    async def send_data(self, data):
        global start_time
        if self.client is None:
            print("No BLE client connected.")
            return

        try:
            await self.client.write_gatt_char(self.char_uuid, data)
        except Exception as e:
            print(f"Failed to write data: {e}")

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            print("Disconnected from the device")

    async def calibrate_steering(self):
        await self.send_data(bytes.fromhex("0d008136115100030000001000"))
        await asyncio.sleep(0.1)
        await self.send_data(bytes.fromhex("0d008136115100030000000800"))
        await asyncio.sleep(0.1)

    async def drive(self, speed=0, angle=0, lights=0x00):
        await self.send_data(bytearray([0x0d,0x00,0x81,0x36,0x11,0x51,0x00,0x03,0x00, speed&0xFF, angle&0xFF, lights&0xFF,0x00]))

# --- Input Handling Abstraction ---
class InputState:
    def __init__(self):
        self.throttle = 0
        self.steering = 0
        self.brake = False
        self.toggle_lights = False

def normalize_axis(value, deadzone=3000, max_abs=32768):
    if abs(value) < deadzone:
        return 0
    return int((value / max_abs) * 100)

def poll_keyboard_state(state, last_toggle):
    # Throttle
    if keyboard.is_pressed('w') or keyboard.is_pressed('up'):
        state.throttle = 50
    elif keyboard.is_pressed('s') or keyboard.is_pressed('down'):
        state.throttle = -50

    # Steering
    if keyboard.is_pressed('a') or keyboard.is_pressed('left'):
        state.steering = -50
    elif keyboard.is_pressed('d') or keyboard.is_pressed('right'):
        state.steering = 50

    # Brake
    if keyboard.is_pressed('space'):
        state.brake = True

    if keyboard.is_pressed('l') and not last_toggle:
        state.toggle_lights = True

# --- Main Async Loop ---

async def main():

    device_name = "Technic Move"
    hub = TechnicMoveHub(device_name)
    if not await hub.scan_and_connect():
        print("Technic hub not found!")
        return

    await hub.calibrate_steering()

    lights = hub.LIGHTS_ON_ON
    toggle_old = False
    throttle_old = 0
    steering_old = 0
    lights_old = 0
    was_brake = False
    steering = 0
    start_time = time.time()

    state = InputState()

    def on_steam_controller_change(buttons, triggers, stick):
        # Map stick vertical to throttle and horizontal to steering

        acccelation = int(triggers[1] / 255 * 100)     # Right trigger
        break_deccel = int(triggers[0] / 255 * 100)    # Left trigger

        state.throttle = acccelation - break_deccel
        state.steering = int((stick[1] / 32768) * 100)   # Horizontal

        state.brake = 'A' in buttons
        state.toggle_lights = 'Y' in buttons and not toggle_old

    asyncio.create_task(
        read_steam_controller(on_steam_controller_change)  # Start reading Steam Controller in background
    )

    try:
         while True:

            throttle = state.throttle
            steering = state.steering
            brake = state.brake
            toggle = state.toggle_lights

            if abs(throttle) < 3:
                throttle = 0
            if abs(steering) < 3:
                steering = 0

            # Toggle lights on key/button press (edge detection)
            if toggle:
                if lights == hub.LIGHTS_OFF_OFF:
                    print("lights on")
                    lights = hub.LIGHTS_ON_ON
                else:
                    print("lights off")
                    lights = hub.LIGHTS_OFF_OFF
            toggle_old = toggle

            if brake and not was_brake:
                await hub.drive(0, steering, hub.LIGHTS_OFF_ON)
                await asyncio.sleep(0.4)
                throttle = 0
                throttle_old = 0

            if not brake and was_brake:
                await hub.drive(throttle, steering, lights)

            was_brake = brake

            if (steering != steering_old or throttle != throttle_old or lights != lights_old) and not brake:
                print("throttle", throttle, "steering", steering)
                await hub.drive(throttle, steering, lights)

            throttle_old = throttle
            steering_old = steering
            lights_old = lights

            sys.stdout.flush()
            await asyncio.sleep(0.05)

    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    asyncio.run(main())

