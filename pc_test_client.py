import socket
import json
import struct
import numpy as np
import cv2

HOST = "127.0.0.1"
PORT = 9999

def send_cmd(cmd):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))

        msg = json.dumps(cmd).encode()
        s.sendall(struct.pack(">I", len(msg)) + msg)

        raw_len = s.recv(4)
        msg_len = struct.unpack(">I", raw_len)[0]

        data = b''
        while len(data) < msg_len:
            data += s.recv(4096)

        return json.loads(data.decode())

def decode_and_show(resp):
    img_bytes = bytes.fromhex(resp["image"])
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    cv2.imshow("Frame", img)
    cv2.waitKey(0)

# -------- TESTS --------
resp = send_cmd([10])
print(resp)
decode_and_show(resp)

send_cmd([98])  # switch mode
send_cmd([1])   # reset

