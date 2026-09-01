#!/usr/bin/env python3
"""BIN→SGO + Virtual-CAN tester
Usage: python bin_to_sgo_can_tester.py <input.bin> [--out <out.sgo>] [--received <recv.sgo>]

Flow:
 - Convert BIN -> SGO using existing bin_to_sgo_v3.py logic
 - Start a virtual-CAN mock ECU that reconstructs SGO sent as raw CAN frames
 - Client streams the SGO in simple 8-byte frames (no ISO-TP) and waits for ACK
 - Compare received SGO with generated SGO and report success rate

Note: This is a test harness only. It uses python-can virtual interface.
"""
import sys
import os
from pathlib import Path
import threading
import time
import struct

# ensure local modules load
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
# import converter class
from bin_to_sgo_v3 import BINtoSGOV3
import can

REQUEST_ID = 0x7E0
RESPONSE_ID = 0x7E8

# Protocol (simple):
#  - Start stream: CAN frame id=REQUEST_ID, data = b"ST" + uint32LE(total_size)
#  - Data frames: id=REQUEST_ID, data = b"D" + seq(1 byte) + up to 6 payload bytes (total 8 bytes)
#  - End stream: id=REQUEST_ID, data = b"EN" + uint32LE(crc32)
#  - ECU replies with ACK: id=RESPONSE_ID, data = b"OK" or b"ER"


def convert_bin(input_path: str, out_path: str = None):
    if not out_path:
        out_path = str(Path(input_path).with_suffix('') ) + '_converted.sgo'
    conv = BINtoSGOV3(input_path, reference_path=None)
    res = conv.convert(output_path=out_path, json_output=None, index_output=None, auto_correct=True, dry_run=False, verbose=False)
    return res['output_file']


def ecu_listener_thread(stop_event: threading.Event, recv_path: Path):
    bus = can.Bus(interface='virtual', channel='vcan0', receive_own_messages=True)
    print('[ECU] listener started')
    buffer = bytearray()
    expected = None
    while not stop_event.is_set():
        msg = bus.recv(timeout=0.5)
        if msg is None:
            continue
        data = bytes(msg.data or b'')
        if len(data) < 2:
            continue
        tag = data[:2]
        if tag == b'ST':
            if len(data) >= 6:
                total = struct.unpack_from('<I', data, 2)[0]
                expected = total
                buffer = bytearray()
                print(f'[ECU] START stream expect {total} bytes')
                # reply OK
                ack = can.Message(arbitration_id=RESPONSE_ID, data=b'OK'+bytes(6), is_extended_id=False)
                bus.send(ack)
        elif tag == b'D_':
            # data frame
            seq = data[2]
            payload = data[3:]
            buffer.extend(payload)
            # occasionally ACK
            if len(buffer) % 1024 < 8:
                ack = can.Message(arbitration_id=RESPONSE_ID, data=b'OK'+bytes(6), is_extended_id=False)
                bus.send(ack)
        elif tag == b'EN':
            # end frame with crc
            if len(data) >= 6:
                crc = struct.unpack_from('<I', data, 2)[0]
                # write file (trim any padding up to expected length)
                recv_path.parent.mkdir(parents=True, exist_ok=True)
                to_write = bytes(buffer[:expected]) if expected is not None else bytes(buffer)
                recv_path.write_bytes(to_write)
                print(f'[ECU] Received end, wrote {len(to_write)} bytes to {recv_path}, crc={crc:08X}')
                # validate crc
                import zlib
                calc = zlib.crc32(bytes(buffer)) & 0xFFFFFFFF
                if calc == crc:
                    ack = can.Message(arbitration_id=RESPONSE_ID, data=b'OK'+bytes(6), is_extended_id=False)
                    bus.send(ack)
                else:
                    ack = can.Message(arbitration_id=RESPONSE_ID, data=b'ER'+bytes(6), is_extended_id=False)
                    bus.send(ack)
                expected = None
        else:
            # ignore or log
            pass
    bus.shutdown()
    print('[ECU] listener stopped')


def client_stream_sgo(sgo_path: Path, timeout: float = 30.0) -> bool:
    bus = can.Bus(interface='virtual', channel='vcan0', receive_own_messages=True)
    data = sgo_path.read_bytes()
    total = len(data)
    # send START
    start = b'ST' + struct.pack('<I', total) + bytes(2)
    bus.send(can.Message(arbitration_id=REQUEST_ID, data=start, is_extended_id=False))
    time.sleep(0.05)
    # send data frames: tag 'D_' (2 bytes), seq, up to 5 bytes payload (to stay within 8 bytes)
    seq = 0
    pos = 0
    while pos < total:
        chunk = data[pos:pos+5]
        payload = b'D_' + bytes([seq & 0xFF]) + chunk
        if len(payload) < 8:
            payload = payload + bytes(8 - len(payload))
        bus.send(can.Message(arbitration_id=REQUEST_ID, data=payload, is_extended_id=False))
        pos += len(chunk)
        seq += 1
        time.sleep(0.001)
    # send END with CRC32
    import zlib
    crc = zlib.crc32(data) & 0xFFFFFFFF
    end = b'EN' + struct.pack('<I', crc) + bytes(2)
    bus.send(can.Message(arbitration_id=REQUEST_ID, data=end, is_extended_id=False))

    # wait for ACK
    startt = time.time()
    ok = False
    while time.time() - startt < timeout:
        msg = bus.recv(timeout=0.5)
        if msg and msg.arbitration_id == RESPONSE_ID:
            d = bytes(msg.data or b'')
            if d.startswith(b'OK'):
                ok = True
                break
            if d.startswith(b'ER'):
                ok = False
                break
    bus.shutdown()
    return ok


def main(argv):
    if len(argv) < 2:
        print('Usage: bin_to_sgo_can_tester.py <input.bin> [--out out.sgo] [--received recv.sgo]')
        return 2
    inp = Path(argv[1])
    out_arg = None
    recv_arg = None
    if '--out' in argv:
        i = argv.index('--out')
        out_arg = argv[i+1]
    if '--received' in argv:
        i = argv.index('--received')
        recv_arg = argv[i+1]
    if not out_arg:
        out_arg = str(inp.with_suffix('') ) + '_converted.sgo'
    if not recv_arg:
        recv_arg = str(Path(out_arg).with_name(Path(out_arg).stem + '_received.sgo'))

    print('[MAIN] Converting', inp)
    sgo_path = Path(convert_bin(str(inp), out_arg))
    print('[MAIN] Converted ->', sgo_path)

    stop_evt = threading.Event()
    recv_path = Path(recv_arg)
    t = threading.Thread(target=ecu_listener_thread, args=(stop_evt, recv_path), daemon=True)
    t.start()
    time.sleep(0.2)
    print('[MAIN] Streaming SGO over virtual CAN...')
    ok = client_stream_sgo(sgo_path)
    # stop listener
    time.sleep(0.2)
    stop_evt.set()
    t.join(1.0)
    if ok and recv_path.exists():
        # compare
        orig = sgo_path.read_bytes()
        rec = recv_path.read_bytes()
        match = orig == rec
        print('[MAIN] Stream result: ACK=', ok, 'match=', match)
        return 0 if match else 3
    print('[MAIN] Stream result: ACK=', ok)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
