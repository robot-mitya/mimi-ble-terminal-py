import argparse
import asyncio

from bleak import BleakClient, BleakGATTCharacteristic
from bleak.exc import BleakError
from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType


BLUEZ_SERVICE_NAME = "org.bluez"


async def get_paired_devices_with_alias():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    introspection = await bus.introspect(BLUEZ_SERVICE_NAME, "/")
    obj = bus.get_proxy_object(BLUEZ_SERVICE_NAME, "/", introspection)
    manager = obj.get_interface("org.freedesktop.DBus.ObjectManager")
    # noinspection PyUnresolvedReferences
    objects = await manager.call_get_managed_objects()

    paired_devices = []
    for path, interfaces in objects.items():
        if "org.bluez.Device1" in interfaces:
            props = interfaces["org.bluez.Device1"]
            paired = props.get("Paired", Variant("b", False)).value
            alias = props.get("Alias", Variant("s", "")).value
            address = props.get("Address", Variant("s", "")).value
            if paired:
                paired_devices.append((alias, address, path))

    return paired_devices


# UART-over-BLE UUIDs (Nordic UART Service, как у micro:bit)
UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_WRITE_UUID   = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # TX from client
UART_READ_UUID    = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # RX to client

async def interactive_session_with_robot(address: str):
    print(f"📡 Connecting to {address}...")

    try:
        async with BleakClient(address) as client:
            if not client.is_connected:
                print("❌ Failed to connect.")
                return

            print(f"✅ Connected to {address}")
            print("💬 Enter commands to send to robot. Type 'q' to quit.\n")

            # Функция обработки входящих сообщений от робота
            def handle_rx(_: BleakGATTCharacteristic, data: bytearray):
                print(f"🤖 {data.decode(errors='ignore').strip()}")

            try:
                await client.start_notify(UART_READ_UUID, handle_rx)
            except Exception as e:
                print(f"⚠️ Failed to start notifications: {e}")
                return

            while True:
                try:
                    command = await asyncio.get_event_loop().run_in_executor(None, input, "> ")

                    if command.strip().lower() == "q":
                        print("👋 Exiting...")
                        break

                    if not command.endswith("\n"):
                        command += "\n"

                    await client.write_gatt_char(UART_WRITE_UUID, command.encode())
                except KeyboardInterrupt:
                    print("\n👋 Ctrl+C pressed, exiting...")
                    break
                except Exception as e:
                    print(f"⚠️ Error during communication: {e}")
                    break

            await client.stop_notify(UART_READ_UUID)
            print("🔌 Disconnected.")

    except BleakError as e:
        print(f"❌ BLE connection error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def main(robot_name: str):
    devices = await get_paired_devices_with_alias()

    print("🔍 Paired devices:")
    for alias, address, _ in devices:
        print(f" - {alias} [{address}]")

    if robot_name:
        for alias, address, _ in devices:
            if alias == robot_name:
                print(f"✅ Found robot with alias '{alias}' at {address}")
                await interactive_session_with_robot(address)
                return
        print(f"❌ No paired device with alias '{robot_name}' found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-name", help="Alias of paired robot in system")
    args = parser.parse_args()

    asyncio.run(main(args.robot_name))
