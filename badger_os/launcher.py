from machine import ADC, I2C, Pin
import gc
import re
import os
import time
import math
import badger2040
from badger2040 import WIDTH
import badger_os
if badger2040.is_wireless() == True:
    import network
import jpegdec

APP_DIR = "/examples"
FONT_SIZE = 2

changed = False
exited_to_launcher = False
woken_by_button = badger2040.woken_by_button()  # Must be done before we clear_pressed_to_wake

if badger2040.pressed_to_wake(badger2040.BUTTON_A) and badger2040.pressed_to_wake(badger2040.BUTTON_C):
    # Pressing A and C together at start quits app
    exited_to_launcher = badger_os.state_clear_running()
    badger2040.reset_pressed_to_wake()
else:
    # Otherwise restore previously running app
    badger_os.state_launch()


display = badger2040.Badger2040()
display.set_font("bitmap8")
display.led(128)

jpeg = jpegdec.JPEG(display.display)

state = {
    "page": 0,
    "running": "launcher"
}

badger_os.state_load("launcher", state)

examples = [x[:-3] for x in os.listdir("/examples") if x.endswith(".py")]

# Approximate center lines for buttons A, B and C
centers = (41, 147, 253)

MAX_PAGE = math.ceil(len(examples) / 3)


def map_value(input, in_min, in_max, out_min, out_max):
    return (((input - in_min) * (out_max - out_min)) / (in_max - in_min)) + out_min


def draw_disk_usage(x):
    _, f_used, _ = badger_os.get_disk_usage()

    display.set_pen(15)
    display.image(
        bytearray(
            (
                0b00000000,
                0b00111100,
                0b00111100,
                0b00111100,
                0b00111000,
                0b00000000,
                0b00000000,
                0b00000001,
            )
        ),
        8,
        8,
        x,
        4,
    )
    display.rectangle(x + 10, 3, 80, 10)
    display.set_pen(0)
    display.rectangle(x + 11, 4, 78, 8)
    display.set_pen(15)
    display.rectangle(x + 12, 5, int(76 / 100.0 * f_used), 6)
    display.text("{:.2f}%".format(f_used), x + 91, 4, WIDTH, 1.0)


def draw_battery_usage(x):

    # Pico W voltage read function by darconeous on reddit with a little help of Kerry Waterfield aka alphanumeric: 
    # https://www.reddit.com/r/raspberrypipico/comments/xalach/comment/ipigfzu/
    # in reference of https://pico.pinout.xyz/ and https://picow.pinout.xyz/
    # the pins and ports are transfered, to make it work on a badger2040 non-W
         
    # these are our reference voltages for a full/empty battery, in volts 
    # the values could vary by battery size/manufacturer so you might need to adjust them
    # full/empty-pairs for some batteries:
    # lipo: 4.2 / 2.8
    # 2xAA/2xAAA alkaline: 3.2 / 2.4
    full_battery = 4.2 
    empty_battery = 2.8 
    vsys = 0

    conversion_factor = 3 * 3.3 / 2**16  # for Badger 2040W internal 3.3V as referece
    little_wait = 0.01  # time slice to wait for vref to stabilize

    if badger2040.is_wireless() == True:
        
        wlan = network.WLAN(network.STA_IF)
        wlan_active = wlan.active()
    
        try:
            # Don't use the WLAN chip for a moment.
            wlan.active(False)
            
        
            # Make sure pin 25 is high.
            Pin(25, mode=Pin.OUT, pull=Pin.PULL_DOWN).high()
  
            # Reconfigure pin 29 as an input.
            Pin(29, Pin.IN, pull=None)

            # reading 'WL_GPIO2' on a picoW tells us whether or not USB power is connected (VBUS Sense)
            # be aware, that on MicroPython v0.0.4 there is a bug and it doesnt work! Stay on v0.0.3!
            vbus = Pin('WL_GPIO2', Pin.IN).value()

            # doing one shot for free
            vsys_sample = ADC(29).read_u16() * conversion_factor
            time.sleep(10 * little_wait)
            
            # we will read 5 times 
            for i in range(5):
                # reading vsys aka battery-level
                vsys_sample = ADC(29).read_u16() * conversion_factor
                vsys = vsys + vsys_sample
                time.sleep(5 * little_wait)

            # arithmetic average over the 5 samples
            vsys = ( vsys / 5 )
                    
        finally:

            # Restore the pin state and possibly reactivate WLAN
            Pin(25, Pin.OUT, value=0, pull=Pin.PULL_DOWN)
            Pin(29, Pin.ALT, pull=Pin.PULL_DOWN, alt=7)
            wlan.active(wlan_active)


    else:
        # Configure pin 29 as an input. (Read VSYS/3 through resistor divider and FET Q1)
        Pin(25, mode=Pin.OUT, pull=Pin.PULL_DOWN).high()
        Pin(29, Pin.IN, pull=None)
        
        # reading pin24 on a pico-non-w tells us whether or not USB power is connected (VBUS Sense)
        vbus = Pin(24, Pin.IN).value()  
        
        # give vref a little time to stabilize
        vsys_sample = ADC(29).read_u16() * conversion_factor
        time.sleep(50 * little_wait) 

        # we well read 5 times 
        for i in range(5):
            # reading vsys aka battery-level
            vsys_sample = ADC(29).read_u16() * conversion_factor
            vsys = vsys + vsys_sample
            time.sleep(5 * little_wait) 
        
        # arithmetic average over the 5 samples
        vsys = ( vsys / 5 )

        
    # convert the val_sys (raw ADC read) into a voltage, and then a percentage
    b_level = 100 * ( ( vsys - empty_battery) / (full_battery - empty_battery) )
    if b_level > 100:
        b_level = 100.00

    display.set_pen(15)
    display.image(
        bytearray(
            (
                0b110011,
                0b001100,
                0b011110,
                0b011110,
                0b010010,
                0b010010,
                0b010010,
                0b011110,
                0b000001,
            )
        ),
        6,
        9,
        x,
        3,
    )
    # assemble horizontal bar-graph beginning at position x+8 (bc. width of 6px the battery symbol)
    # outer white box
    display.rectangle(x + 8, 3, 80, 10)
    display.set_pen(0)
    # inner black box
    display.rectangle(x + 9, 4, 78, 8)
    # white bar according to percentage
    display.set_pen(15)
    #print(f"b_level: {b_level}")

    # reading 'WL_GPIO2' on a picoW or pin 24 on pico tells us whether or not USB power is connected (VBUS Sense)

    # if it's not plugged into USB power...
    if vbus == False:
        # if vbus is false, display the battery status:
        # bar starts at coordinates x+10,5 and 6px high max length 76px (accordingly to percentage)
        display.rectangle(x + 10, 5, int(76 / 100.0 * b_level), 6) 
        display.text("{:.2f}%".format(b_level), x + 91, 4, WIDTH, 1.0)
    else:
        # fake full power on USB when "vbus" is true
        display.rectangle(x + 10, 5, int(76 / 100.0 * 100 ), 6) 
        display.text("USB", x + 91, 4, WIDTH, 1.0)


def render():
    display.set_pen(15)
    display.clear()
    display.set_pen(0)

    max_icons = min(3, len(examples[(state["page"] * 3):]))

    for i in range(max_icons):
        x = centers[i]
        label = examples[i + (state["page"] * 3)]
        icon_label = label.replace("_", "-")
        icon = f"{APP_DIR}/icon-{icon_label}.jpg"
        label = label.replace("_", " ")
        jpeg.open_file(icon)
        jpeg.decode(x - 26, 30)
        display.set_pen(0)
        w = display.measure_text(label, FONT_SIZE)
        display.text(label, int(x - (w / 2)), 16 + 80, WIDTH, FONT_SIZE)

    for i in range(MAX_PAGE):
        x = 286
        y = int((128 / 2) - (MAX_PAGE * 10 / 2) + (i * 10))
        display.set_pen(0)
        display.rectangle(x, y, 8, 8)
        if state["page"] != i:
            display.set_pen(15)
            display.rectangle(x + 1, y + 1, 6, 6)

    display.set_pen(0)
    display.rectangle(0, 0, WIDTH, 16)
    draw_disk_usage(50)
    draw_battery_usage(175)
    display.set_pen(15)
    display.text("badgerOS", 4, 4, WIDTH, 1.0)

    display.update()


def wait_for_user_to_release_buttons():
    while display.pressed_any():
        time.sleep(0.01)


def launch_example(index):
    wait_for_user_to_release_buttons()

    file = examples[(state["page"] * 3) + index]
    file = f"{APP_DIR}/{file}"

    for k in locals().keys():
        if k not in ("gc", "file", "badger_os"):
            del locals()[k]

    gc.collect()

    badger_os.launch(file)


def button(pin):
    global changed
    changed = True

    if pin == badger2040.BUTTON_A:
        launch_example(0)
    if pin == badger2040.BUTTON_B:
        launch_example(1)
    if pin == badger2040.BUTTON_C:
        launch_example(2)
    if pin == badger2040.BUTTON_UP:
        if state["page"] > 0:
            state["page"] -= 1
        render()
    if pin == badger2040.BUTTON_DOWN:
        if state["page"] < MAX_PAGE - 1:
            state["page"] += 1
        render()


if exited_to_launcher or not woken_by_button:
    wait_for_user_to_release_buttons()
    display.set_update_speed(badger2040.UPDATE_MEDIUM)
    render()

display.set_update_speed(badger2040.UPDATE_FAST)

while True:
    # Sometimes a button press or hold will keep the system
    # powered *through* HALT, so latch the power back on.
    display.keepalive()

    if display.pressed(badger2040.BUTTON_A):
        button(badger2040.BUTTON_A)
    if display.pressed(badger2040.BUTTON_B):
        button(badger2040.BUTTON_B)
    if display.pressed(badger2040.BUTTON_C):
        button(badger2040.BUTTON_C)

    if display.pressed(badger2040.BUTTON_UP):
        button(badger2040.BUTTON_UP)
    if display.pressed(badger2040.BUTTON_DOWN):
        button(badger2040.BUTTON_DOWN)

    if changed:
        badger_os.state_save("launcher", state)
        changed = False

    display.halt()
