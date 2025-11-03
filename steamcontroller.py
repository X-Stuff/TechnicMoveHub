import pywinusb.hid as hid
import asyncio
import struct

VENDOR_ID = 0x28de  # Valve
PRODUCT_ID = 0x1102 # Steam Controller (may vary)

BUTTONS_MAP = {
    0: "RT_BTN",            # Right Trigger Button (full press with click)
    1: "LT_BTN",            # Left Trigger Button (full press with click)
    2: "RB",                # Right Bumper
    3: "LB",                # Left Bumper
    4: "Y",                 # Top Button (Y)
    5: "B",                 # Right Button (B)
    6: "X",                 # Left Button (X)
    7: "A",                 # Bottom Button (A)
    8: "D_PAD_UP",          # D-Pad Buttons
    9: "D_PAD_RIGHT",       # D-Pad Buttons
    10: "D_PAD_LEFT",       # D-Pad Buttons
    11: "D_PAD_DOWN",       # D-Pad Buttons
    12: "BACK",             # Back Button
    13: "STEAM",            # Steam Button (Center)
    14: "START",            # Start Button
    15: "LEFT_GRIP",        # Left Grip Button (back side of controller)
    16: "RIGHT_GRIP",       # Right Grip Button (back side of controller)
    17: "LEFT_PAD_CLICK",   # Hard press on left touchpad
    18: "RIGHT_PAD_CLICK",  # Hard press on right touchpad
    19: "LEFT_TOUCH",       # Touch on left touchpad
    20: "RIGHT_TOUCH",      # Touch on right touchpad
    21: "21",
    22: "LS_CLICK",         # Left Stick Click
    23: "23",
    24: "24",
}

PACKET_PREAMBLE = [3, 192]

INPUT_PACKET_TYPE   = 0b00000100
REPORT_PACKET_TYPE  = 0b00000101

PACKET_BUTTON_MASK  = 0b00010000
PACKET_TRIGGER_MASK = 0b00100000
PACKET_UNKNOWN_MASK = 0b01000000
PACKET_STICK_MASK   = 0b10000000


def _is_report_packet(packet_type):
    return (packet_type & 0x0F) == REPORT_PACKET_TYPE

def _is_data_packet(packet_type):
    return (packet_type & 0x0F) == INPUT_PACKET_TYPE

def _has_any_input(packet_type):
    return (packet_type & 0xF0) != 0

def _has_buttons(packet_type):
    return (packet_type & PACKET_BUTTON_MASK) != 0

def _has_triggers(packet_type):
    return (packet_type & PACKET_TRIGGER_MASK) != 0

def _has_stick(packet_type):
    return (packet_type & PACKET_STICK_MASK) != 0


def parse_buttons(btn_bytes):
    """
    data[4:7]
    """
    pressed = []
    for byte_index, btn_byte in enumerate(btn_bytes):
        for bit in range(8):
            btn_num = byte_index * 8 + bit
            if btn_num in BUTTONS_MAP and (btn_byte & (1 << bit)):
                pressed.append(BUTTONS_MAP[btn_num])
    return pressed


def parse_triggers(trigger_bytes):
    """
    data[4:5]
    """
    left = trigger_bytes[0]
    right = trigger_bytes[1]
    return left, right

def parse_stick(stick_bytes):
    """
    data[4:8]
    Parse bytes 4-5 as int16 (vertical), bytes 6-7 as int16 (horizontal)
    """
    horizontal = struct.unpack_from('<h', bytes(stick_bytes[0:2]))[0]
    vertical = struct.unpack_from('<h', bytes(stick_bytes[2:4]))[0]
    return vertical, horizontal


def find_steam_controller():
    vavle_devices = hid.HidDeviceFilter(vendor_id=VENDOR_ID).get_devices()

    print("Valve devices found:", len(vavle_devices))
    for device in vavle_devices:
        print(f"Vendor ID: {hex(device.vendor_id)}, Product ID: {hex(device.product_id)}")
        print(f"  Manufacturer: {device.vendor_name}")
        print(f"  Product: {device.product_name}")
        print(f"  Serial: {device.serial_number}")

    return vavle_devices[0] if vavle_devices else None

async def read_steam_controller(on_change=None):
    """
    Asynchronously read input from the Steam Controller and call on_change
    callback with the current state when input changes.
    """
    device = find_steam_controller()
    if not device:
        print("Steam Controller not found.")
        return

    print(f"Found Steam Controller: {device.vendor_name} {device.product_name}")

    loop = asyncio.get_event_loop()
    data_queue = asyncio.Queue()

    def raw_handler(data):
        loop.call_soon_threadsafe(data_queue.put_nowait, data)

    device.open()
    device.set_raw_data_handler(raw_handler)

    try:
        buttons = set()
        prev_buttons = set()

        triggers = (0, 0)
        prev_triggers = (0, 0)

        stick = (0, 0)
        prev_stick = (0, 0)

        while True:
            data = await data_queue.get()

            if (data[0] != PACKET_PREAMBLE[0] or data[1] != PACKET_PREAMBLE[1]):
                print(f"Unknown preable: packet: {data}")
                continue  # Ignore unknown packets

            # The 3rd byte indicates the packet type
            packet_type = data[2]

            if _is_report_packet(packet_type):
                continue  # Ignore report packets

            if not _is_data_packet(packet_type):
                print(f"Unknown Non-data packet received. {data}")
                continue  # Ignore non-data packets

            if not _has_any_input(packet_type):
                continue  # No input data in this packet

            offset = 0
            if _has_buttons(packet_type):
                buttons = set(parse_buttons(data[offset + 4: offset + 7]))
                offset += 3

            if _has_triggers(packet_type):
                triggers = parse_triggers(data[offset + 4: offset + 6])
                offset += 2

            if _has_stick(packet_type):
                stick = parse_stick(data[offset + 4: offset + 8])
                offset += 4

            if offset == 0:
                print(f"UNKNOWN TYPE: data:{data}")

            if buttons != prev_buttons or triggers != prev_triggers or stick != prev_stick:
                if on_change:
                    loop.call_soon_threadsafe(on_change, buttons, triggers, stick)

            prev_buttons = buttons
            prev_triggers = triggers
            prev_stick = stick

    except asyncio.CancelledError:
        pass
    finally:
        device.close()
        print("Device closed.")


if __name__ == "__main__":

    def on_change(buttons, triggers, stick):
        print(f"Buttons: {sorted(buttons)}, Triggers: L={triggers[0]} R={triggers[1]}, Stick: V={stick[0]} H={stick[1]}")

    try:
        asyncio.run(read_steam_controller(on_change=on_change))
    except KeyboardInterrupt:
        print("Stopped by user.")