import ctypes
import time
import numpy as np
import cv2
import bettercam

user32 = ctypes.windll.user32

# ==== Settings ====
# Screen capture
REGION = (0, 0, 2560, 1440)     # capture area: (left, top, right, bottom)
SIZE = 84                       # size of downscaled image

# Target detection
HSV_LOW = (80, 120, 120)        # Target colour range
HSV_HIGH = (100, 255, 255)
MIN_AREA = 2                    # min target size
MAX_AREA = 32000                # max target size

# Aiming
GAIN = 0.5                      # sensitivity multiplier
MAX_STEP = 100                  # max mouse movement per iteration
DEADZONE = 0                    # do not move the mouse for smaller corrections

# Shooting
CLICK_RADIUS = 10               # shoot when the target center is within this many px of screen center
CLICK_COOLDOWN = 0.25           # min time between two shots

# Timing
AFTER_CLICK = 0.15              # wait for the target to disappear
SETTLE = 0.03                   # wait for the next frame

# Modes
RETURN_HOME = False             # move the crosshair back to its start position after each shot
SHOW_DEBUG = False              # show mask info
# ==================

# Mouse starting location
home_x, home_y = 0, 0

# Timestamp of the last shot used for click cooldown.
last_click = 0.0

def move_mouse(dx, dy):
    """Move mouse to new location"""
    global home_x, home_y
    ix, iy = int(dx), int(dy)
    if ix == 0 and iy == 0:
        return
    user32.mouse_event(0x0001, ix, iy, 0, 0)
    home_x += ix
    home_y += iy


def return_home():
    """Move mouse to starting location"""
    global home_x, home_y
    if home_x or home_y:
        user32.mouse_event(0x0001, -home_x, -home_y, 0, 0)
        home_x, home_y = 0, 0
        time.sleep(SETTLE)




def click():
    """Mouse left click with a cooldown"""
    global last_click
    now = time.perf_counter()
    if now - last_click < CLICK_COOLDOWN:
        return False
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.015)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    last_click = time.perf_counter()
    return True


def esc_pressed():
    """esc button to stop script"""
    return user32.GetAsyncKeyState(0x1B) & 0x8000


def clamp(v, lim):
    """Limit v to max step size"""
    return max(-lim, min(lim, v))


def find_target(img):
    """Find the target closest to the screen centre.

    Returns (dx, dy): offset of the target centre from the image centre in
    pixels.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LOW, HSV_HIGH)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    if SHOW_DEBUG:
        cv2.imshow("mask", cv2.resize(mask, (640, 360)))
        cv2.waitKey(1)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = img.shape[:2]
    if SHOW_DEBUG:
        areas = sorted([int(cv2.contourArea(c)) for c in cnts], reverse=True)[:5]
        print("Number of targets:", len(cnts), "Area:", areas)

    best, best_dist = None, float("inf")
    for c in cnts:
        area = cv2.contourArea(c)
        if not (MIN_AREA < area < MAX_AREA):
            continue
        x, y, w, h = cv2.boundingRect(c)
        if h == 0 or not (0.6 < w / h < 1.6):
            continue
        if area / (w * h) < 0.3:
            continue
        dx = (x + w / 2) - W / 2
        dy = (y + h / 2) - H / 2
        d = dx * dx + dy * dy
        if d < best_dist:
            best, best_dist = (dx, dy), d
    return best


def cam_init():
    """Create cam and start screen capture"""
    cam = bettercam.create(output_color="BGR")
    cam.start(region=REGION, target_fps=60)
    return cam


def frame(cam):
    """Grab the latest frame"""
    img = None
    while img is None:
        img = cam.get_latest_frame()
    small = cv2.resize(img, (SIZE, SIZE))
    obs = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)[..., None]
    return img, obs


def main():
    time.sleep(1)  # Delay
    print("Start")
    cam = cam_init()
    try:
        while not esc_pressed(): # stop condition
            img, obs = frame(cam)
            target = find_target(img)
            if target is None:
                continue

            dx, dy = target
            mx = clamp(dx * GAIN, MAX_STEP)
            my = clamp(dy * GAIN, MAX_STEP)

            # Move only if the error is outside the deadzone
            if abs(mx) >= DEADZONE or abs(my) > DEADZONE:
                move_mouse(mx, my)
                time.sleep(SETTLE)

            # Shoot if targets center is closer than click radius
            if abs(dx) < CLICK_RADIUS and abs(dy) < CLICK_RADIUS:
                if click():
                    time.sleep(AFTER_CLICK)
                    if RETURN_HOME:
                        return_home()
        print("Stop")
    finally:
        if RETURN_HOME:
            return_home()
        cam.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()