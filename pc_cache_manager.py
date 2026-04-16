import os
import re

import cv2
import numpy as np


TEST_MODE = False
FPS = 60.0
IMAGE_SHAPE = (1080, 1920, 3)
CACHE_ROOT = os.path.join(os.path.dirname(__file__), "cache")
LEFT_CACHE_DIR = os.path.join(CACHE_ROOT, "left_image")
RIGHT_CACHE_DIR = os.path.join(CACHE_ROOT, "right_image")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

CURRENT_INDEX = None


def get_dummy_image(value=0):
    img = np.full(IMAGE_SHAPE, value, dtype=np.uint8)
    cv2.putText(
        img,
        "PC FAKE SOC",
        (50, IMAGE_SHAPE[0] // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (255, 255, 255),
        3,
    )
    return img


def get_frame_token(filename):
    stem, _ = os.path.splitext(filename)
    match = re.search(r"(\d+)$", stem)
    if match is not None:
        return match.group(1)
    return stem


def sort_frame_tokens(tokens):
    def sort_key(token):
        if token.isdigit():
            return (0, int(token))
        return (1, token)

    return sorted(tokens, key=sort_key)


def build_image_map(folder_path):
    image_map = {}

    if not os.path.isdir(folder_path):
        return image_map

    for entry in os.listdir(folder_path):
        file_path = os.path.join(folder_path, entry)
        if not os.path.isfile(file_path):
            continue

        _, extension = os.path.splitext(entry)
        if extension.lower() not in IMAGE_EXTENSIONS:
            continue

        frame_token = get_frame_token(entry)
        image_map[frame_token] = file_path

    return image_map


def load_rgb_image(file_path):
    image = cv2.imread(file_path, cv2.IMREAD_COLOR)
    if image is None:
        return None
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def get_timestamp(frame_num):
    if frame_num is None or frame_num < 0:
        return 0.0
    return frame_num / FPS


def resolve_frame_index(command, shared_tokens):
    global CURRENT_INDEX

    if not shared_tokens:
        return None

    if CURRENT_INDEX is None or CURRENT_INDEX >= len(shared_tokens):
        CURRENT_INDEX = len(shared_tokens) - 1

    cmd = command[0]

    if cmd == 10:
        CURRENT_INDEX = len(shared_tokens) - 1

    elif cmd == 11:
        offset = max(0, int(command[1]))
        CURRENT_INDEX = max(0, CURRENT_INDEX - offset)

    elif cmd == 12:
        offset = max(0, int(command[1]))
        CURRENT_INDEX = min(len(shared_tokens) - 1, CURRENT_INDEX + offset)

    elif cmd == 15:
        requested = str(int(command[1]))
        if requested not in shared_tokens:
            return None
        CURRENT_INDEX = shared_tokens.index(requested)

    else:
        return None

    return CURRENT_INDEX


def get_dummy_frame(command):
    frame_num = 0
    if len(command) > 1:
        frame_num = int(command[1])

    return {
        "frame": frame_num,
        "timestamp": get_timestamp(frame_num),
        "left_image": get_dummy_image(120),
        "right_image": get_dummy_image(125),
    }


def get_frame(command):
    left_map = build_image_map(LEFT_CACHE_DIR)
    right_map = build_image_map(RIGHT_CACHE_DIR)
    shared_tokens = sort_frame_tokens(set(left_map.keys()) & set(right_map.keys()))

    if TEST_MODE or not shared_tokens:
        return get_dummy_frame(command)

    frame_index = resolve_frame_index(command, shared_tokens)
    if frame_index is None:
        return None

    frame_token = shared_tokens[frame_index]
    left_image = load_rgb_image(left_map[frame_token])
    right_image = load_rgb_image(right_map[frame_token])
    if left_image is None or right_image is None:
        return None

    if frame_token.isdigit():
        frame_num = int(frame_token)
    else:
        frame_num = -1

    return {
        "frame": frame_num,
        "timestamp": get_timestamp(frame_num),
        "left_image": left_image,
        "right_image": right_image,
    }
