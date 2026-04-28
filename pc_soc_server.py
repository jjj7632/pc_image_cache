#!/usr/bin/env python3

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from shared_protocol.numpysocket import NumpySocket
from shared_protocol.soc_protocol import *
from pc_cache_manager import get_frame

IMAGE_SHAPE = (1080, 1920, 3)   # MUST match pc_cache_manager
PORT = 9999


class FakeFpgaCache:
    def submit_frame(self, frame_number, image_data):
        pass

    def read_result(self):
        return {"x": 0.0, "y": 0.0, "z": 0.0}


class PCSoCServer:
    def __init__(self):
        self.sock = NumpySocket(image_shape=IMAGE_SHAPE)
        self.protocol = SoCProtocol(
            command_sender=self.send_command,
            fpga_cache=FakeFpgaCache()
        )

    # -------- SEND COMMAND TO MATLAB --------
    def send_command(self, cmd_array):
        cmd = cmd_array[0]

        self.sock.sendCmd(cmd)

        if cmd == CMD_LOG_DATA:
            frame_number = int(cmd_array[1])
            self.sock.sendUint32(frame_number)
            self.sock.sendFloat32(cmd_array[2])
            self.sock.sendFloat32(cmd_array[3])
            self.sock.sendFloat32(cmd_array[4])

        elif cmd in [
            CMD_REQUEST_NTH_PREVIOUS_IMAGE,
            CMD_REQUEST_NTH_NEXT_IMAGE,
        ]:
            self.sock.sendInt32(cmd_array[1])

        elif cmd == CMD_REQUEST_IMAGE_AT_FRAME:
            frame_number = UNKNOWN_FRAME_NUMBER if cmd_array[1] is None else int(cmd_array[1])
            self.sock.sendUint32(frame_number)

        elif cmd == CMD_SEND_CALL:
            self.sock.sendUint8(cmd_array[1])

        elif cmd == CMD_SLAVE_MODE_READY:
            pass

        elif cmd == CMD_STOP_CAPTURE:
            pass

    # -------- HANDLE MATLAB REQUEST --------
    def handle_matlab_request(self, cmd):
        if cmd == CMD_REQUEST_LATEST_IMAGE:
            frame_data = get_frame([10])

        elif cmd == CMD_REQUEST_NTH_PREVIOUS_IMAGE:
            offset = self.sock.receiveInt32()
            frame_data = get_frame([11, offset])

        elif cmd == CMD_REQUEST_NTH_NEXT_IMAGE:
            offset = self.sock.receiveInt32()
            frame_data = get_frame([12, offset])

        elif cmd == CMD_REQUEST_IMAGE_AT_FRAME:
            frame_num = self.sock.receiveUint32()
            if frame_num == UNKNOWN_FRAME_NUMBER:
                frame_num = None
            frame_data = get_frame([15, frame_num])

        else:
            print("Unknown request:", cmd)
            return

        if frame_data is None:
            print("No frame available for request:", cmd)
            return

        frame_number = frame_data["frame"]
        left_image = frame_data["left_image"]
        right_image = frame_data["right_image"]

        # Send stereo image back to MATLAB
        self.sock.sendCmd(CMD_PROCESS_IMAGE)
        self.sock.sendUint32(frame_number)
        self.sock.send(left_image)
        self.sock.send(right_image)

    # -------- MAIN LOOP --------
    def run(self):
        print("[INFO] Waiting for MATLAB connection...")
        self.sock.startServer(PORT)

        print("[INFO] MATLAB connected")

        while True:
            try:
                self.protocol.drive()
                cmd = self.sock.receiveCmd()
                if cmd is None:
                    break

                print("[DEBUG] Received CMD:", cmd)

                # MATLAB asking for image
                if cmd in [
                    CMD_REQUEST_LATEST_IMAGE,
                    CMD_REQUEST_NTH_PREVIOUS_IMAGE,
                    CMD_REQUEST_NTH_NEXT_IMAGE,
                    CMD_REQUEST_IMAGE_AT_FRAME
                ]:
                    self.handle_matlab_request(cmd)

                # MATLAB sending image 
                elif cmd == CMD_PROCESS_IMAGE:
                    frame_number = self.sock.receiveUint32()
                    if frame_number == UNKNOWN_FRAME_NUMBER:
                        frame_number = None
                    left_image = self.sock.receive()
                    right_image = self.sock.receive()

                    result = self.protocol.handle_incoming_command(
                        [CMD_PROCESS_IMAGE, frame_number, {
                            "left_image": left_image,
                            "right_image": right_image
                        }]
                    )

                    print("[RESULT]", result)

                elif cmd == CMD_RESET:
                    self.protocol.handle_incoming_command([CMD_RESET])

                elif cmd == CMD_SLAVE_MODE:
                    self.protocol.handle_incoming_command([CMD_SLAVE_MODE])

                else:
                    print("[WARN] Unknown CMD:", cmd)

            except Exception as e:
                print("[ERROR]", e)
                break

        self.sock.close()


if __name__ == "__main__":
    server = PCSoCServer()
    server.run()
