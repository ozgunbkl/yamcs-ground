#!/usr/bin/env python3

import binascii
import io
import socket
import sys
import argparse
import struct

from struct import unpack_from
from threading import Thread
from time import sleep

parser = argparse.ArgumentParser(description='Yamcs Simulator')
parser.add_argument('--testdata', type=str, default='testdata.ccsds', help='simulated testdata.ccsds data')
parser.add_argument('--tm_host',    type=str, default='127.0.0.1', help='TM host')
parser.add_argument('--tm_port',    type=int, default=10015,       help='TM port')
parser.add_argument('-r', '--rate', type=int, default=1,           help='TM playback rate. 1 = 1Hz, 10 = 10Hz, etc.')
parser.add_argument('--tc_host', type=str, default='127.0.0.1', help='TC host')
parser.add_argument('--tc_port', type=int, default=10025 ,      help='TC port')

args = vars(parser.parse_args())

TEST_DATA = args['testdata']
TM_SEND_ADDRESS = args['tm_host']
TM_SEND_PORT    = args['tm_port']
RATE            = args['rate']
TC_RECEIVE_ADDRESS = args['tc_host']
TC_RECEIVE_PORT    = args['tc_port']

def send_event(simulator, message):
    """Send event message to YAMCS on APID 2000"""
    tm_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    apid = 2000
    seq_count = simulator.event_seq_count
    simulator.event_seq_count += 1
    
    # CCSDS Primary Header (6 bytes)
    # Version=0, Type=0 (TM), SecHdr=0, APID=2000
    word1 = (0 << 13) | (0 << 12) | (0 << 11) | apid
    # SeqFlags=3 (standalone), SeqCount
    word2 = (3 << 14) | (seq_count & 0x3FFF)
    # Packet length = 64 bytes of data - 1 = 63
    word3 = 63
    
    header = struct.pack('>HHH', word1, word2, word3)
    
    # Pack message into 64 bytes (512 bits as defined in XTCE)
    payload = message.encode('ascii').ljust(64, b'\0')
    
    packet = header + payload
    
    tm_socket.sendto(packet, (TM_SEND_ADDRESS, TM_SEND_PORT))
    tm_socket.close()
    
    print(f"\n[EVENT] {message}")

def send_tm(simulator):
    tm_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        with io.open(TEST_DATA, 'rb') as f:
            header = bytearray(6)
            while f.readinto(header) == 6:
                (packet_len,) = unpack_from('>H', header, 4)
                packet = bytearray(packet_len + 7)
                f.seek(-6, io.SEEK_CUR)
                f.readinto(packet)

                # FIXED: Inject voltage into Battery1_Temp at correct offset
                # Packet structure (from XTCE analysis):
                # Bytes 0-5:   CCSDS Header
                # Bytes 6-9:   EpochUSNO
                # Bytes 10-13: OrbitNumberCumulative
                # Bytes 14-17: ElapsedSeconds
                # Bytes 18-21: A
                # Bytes 22-25: Height
                # Bytes 26-37: Position (3 floats)
                # Bytes 38-49: Velocity (3 floats)
                # Bytes 50-53: Latitude
                # Bytes 54-57: Longitude
                # Bytes 58-61: Battery1_Voltage
                # Bytes 62-65: Battery2_Voltage
                # Bytes 66-69: Battery1_Temp  ← WE INJECT HERE!
                # Bytes 70-73: Battery2_Temp
                
                if len(packet) >= 70:
                    voltage_bytes = struct.pack('>f', simulator.battery_voltage)
                    packet[66:70] = voltage_bytes  # Battery1_Temp offset
                    
                    # Also update Battery1_Voltage for completeness
                    packet[58:62] = voltage_bytes

                tm_socket.sendto(packet, (TM_SEND_ADDRESS, TM_SEND_PORT))
                simulator.tm_counter += 1
                sleep(1 / simulator.rate)

def receive_tc(simulator):
    tc_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tc_socket.bind((TC_RECEIVE_ADDRESS, TC_RECEIVE_PORT))
    
    print(f"[TC] Listening on {TC_RECEIVE_ADDRESS}:{TC_RECEIVE_PORT}")
    
    while True:
        data, addr = tc_socket.recvfrom(4096)
        
        if len(data) < 8:
            print(f"[TC] Received short packet: {len(data)} bytes")
            continue
            
        # Extract command ID from bytes 6-7 (after CCSDS header)
        cmd_id = struct.unpack('>H', data[6:8])[0]
        
        print(f"\n[TC] Received command ID: 0x{cmd_id:04X} ({cmd_id})")
        
        if cmd_id == 2:  # SwitchVoltageOn
            simulator.battery_voltage = 12.5
            send_event(simulator, "INFO: Battery 1 Switched ON - Voltage: 12.5V")
            print(f"[CMD] Battery ON → 12.5V")
            
        elif cmd_id == 3:  # SwitchVoltageOff
            simulator.battery_voltage = 0.0
            send_event(simulator, "INFO: Battery 1 Switched OFF - Voltage: 0.0V")
            print(f"[CMD] Battery OFF → 0.0V")
            
        elif cmd_id == 1:  # Reboot
            send_event(simulator, "WARN: Reboot command received - System restarting")
            print(f"[CMD] Reboot commanded")
        else:
            send_event(simulator, f"WARN: Unknown command ID: {cmd_id}")
            print(f"[CMD] Unknown command: {cmd_id}")

        simulator.last_tc = data
        simulator.tc_counter += 1

class Simulator():
    def __init__(self, rate):
        self.tm_counter = 0
        self.tc_counter = 0
        self.last_tc = None
        self.rate = rate
        self.battery_voltage = 0.0
        self.event_seq_count = 0

    def start(self):
        Thread(target=send_tm, args=(self,), daemon=True).start()
        Thread(target=receive_tc, args=(self,), daemon=True).start()

    def print_status(self):
        cmdhex = binascii.hexlify(self.last_tc).decode('ascii') if self.last_tc else "None"
        return f'TM: {self.tm_counter} | TC: {self.tc_counter} | Battery: {self.battery_voltage:.1f}V | Last: {cmdhex[:16]}...'

if __name__ == '__main__':
    simulator = Simulator(RATE)
    simulator.start()
    
    print("=" * 80)
    print("YAMCS SIMULATOR STARTED")
    print("=" * 80)
    print(f"Telemetry:  Sending to {TM_SEND_ADDRESS}:{TM_SEND_PORT}")
    print(f"Telecommand: Listening on {TC_RECEIVE_ADDRESS}:{TC_RECEIVE_PORT}")
    print(f"Playback rate: {RATE} Hz")
    print(f"Test data: {TEST_DATA}")
    print("=" * 80)
    print("\nWaiting for commands...")
    print("(Try: SwitchVoltageOn, SwitchVoltageOff, Reboot)\n")
    
    try:
        prev_status = None
        while True:
            status = simulator.print_status()
            if status != prev_status:
                sys.stdout.write('\r' + " " * 100 + '\r' + status)
                sys.stdout.flush()
                prev_status = status
            sleep(0.5)
    except KeyboardInterrupt:
        print("\n\nSimulator stopped.")