import numpy as np
import cv2

TEST_MODE = True

IMAGE_SHAPE = (480, 640, 3)

def get_dummy_image():
    img = np.zeros(IMAGE_SHAPE, dtype=np.uint8)
    cv2.putText(img, "PC FAKE SOC", (50, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
    return img

def get_frame(command):
    frame_num = 0

    if len(command) > 1:
        frame_num = command[1]

    if TEST_MODE:
        img = get_dummy_image()
    else:
        img = get_dummy_image()

    return {
        "frame": frame_num,
        "timestamp": frame_num / 60.0,
        "image": img
    }


