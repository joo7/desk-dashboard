#!/usr/bin/env python3
"""Laptop helper for the phone dashboard.  Run: python3 tools/sync.py <command>

  setup                  one-time: auto brightness, stay awake, Wi-Fi adb, first push (phone on USB)
  app                    install the Desk app (DeskDash.apk): full screen, starts on boot; then push
  doctor                 run every check and show timings (use this when something is slow)
  push                   send everything to the phone and open it (USB or Wi-Fi)
  image <file>           make this the picture (resized to the screen if ImageMagick exists) and push
  photos <folder>        send all pictures in a folder (full resolution, colour); they rotate on the phone
  todo list|add "text"|done N|undone N|rm N|edit     change the to-do list and push
  tasks                  just rebuild tasks.js from todo.txt
  (weather, air quality, sunrise/sunset and location are handled on the phone; settings are in web/data.js)
  fullscreen on|off      hide the phone's status and navigation bars in the Browser app
  location [on]          check the phone's location service ('on' switches it on, GPS + Wi-Fi)

Paths: the page lives in web/, the app in dist/DeskDash.apk (or android/build/ after ./build.sh).
Every adb call is timed and written to sync.log in the repo folder (not committed).
"""
import json, os, re, shutil, socket, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo folder
WEB = os.path.join(ROOT, "web")                                       # everything sent to the phone
DEST, PORT = "/sdcard/dash", "5555"
TODO, IPFILE = os.path.join(WEB, "todo.txt"), os.path.join(ROOT, ".phone_ip")
LOG, T0, SER = os.path.join(ROOT, "sync.log"), time.time(), None
HINT = {"unauthorized": "-> unlock the phone and tap OK on the 'Allow USB debugging' pop-up",
        "offline": "-> unplug and replug the cable, or toggle USB debugging off and on"}


def log(msg):
    line = "[%6.1fs] %s" % (time.time() - T0, msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + line + "\n")


def step(msg):
    log("== " + msg)


def adb(*a, timeout=30):
    t = time.time()
    try:
        r = subprocess.run(["adb", *a], capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        out = "TIMEOUT after %ds" % timeout
    except FileNotFoundError:
        sys.exit("adb not found. Install it with: sudo apt install adb")
    last = out.splitlines()[-1][:90] if out else ""
    log("adb %s  (%.1fs) %s" % (" ".join(a)[:60], time.time() - t, last))
    return out


def devices():
    out = adb("devices", timeout=20)
    if "TIMEOUT" in out:
        log("adb server looks stuck: restarting it")
        adb("kill-server", timeout=10)
        out = adb("devices", timeout=20)
    ok = []
    for l in out.splitlines():
        if "\t" in l:
            s, st = l.split("\t", 1)
            if st == "device":
                ok.append(s)
            else:
                log("WARNING: %s is '%s' %s" % (s, st, HINT.get(st, "")))
    return ok


def connect():
    """Use USB if plugged in, otherwise Wi-Fi using the IP saved by 'setup'."""
    global SER
    d = devices()
    if os.path.exists(IPFILE) and not any(":" in s for s in d):
        log("trying Wi-Fi at " + open(IPFILE).read().strip())
        adb("connect", open(IPFILE).read().strip() + ":" + PORT, timeout=8)
        d = devices()
    if not d:
        sys.exit("Phone not found. Plug in USB (debugging on), or run: python3 tools/sync.py setup")
    for s in sorted(d, key=lambda x: ":" not in x):  # Wi-Fi first: the USB link keeps freezing
        SER = s
        if "ok" in run("shell", "echo", "ok", timeout=6):
            log("using %s (%s)" % (SER, "Wi-Fi" if ":" in SER else "USB"))
            return
        log("%s is listed but not answering, trying the next one" % s)
    sys.exit("Phone is listed but frozen. Unplug USB for 5s and replug (or toggle USB debugging), then retry.")


def run(*a, timeout=30):
    return adb("-s", SER, *a, timeout=timeout)


def read_todo():
    return open(TODO).read().splitlines() if os.path.exists(TODO) else []


def make_tasks():
    items = []
    for line in read_todo():
        line = line.strip()
        if line:
            items.append({"t": re.sub(r"^\[[ xX]\]\s*", "", line), "done": line.lower().startswith("[x]")})
    with open(os.path.join(WEB, "tasks.js"), "w") as f:
        f.write("var TODO = " + json.dumps(items, ensure_ascii=False) + ";\n")
    log("tasks.js rebuilt (%d items)" % len(items))


def push():
    step("sending files")
    connect()
    make_tasks()
    if not os.path.exists(os.path.join(WEB, "photos.js")):
        open(os.path.join(WEB, "photos.js"), "w").write("var PHOTOS = [];\n")
    run("shell", "mkdir", "-p", DEST)
    for name in ("index.html", "data.js", "tasks.js", "photos.js", "photo.jpg"):
        path = os.path.join(WEB, name)
        if os.path.exists(path):
            log("pushing %s (%d KB)" % (name, os.path.getsize(path) // 1024))
            run("push", path, DEST + "/" + name, timeout=90)
    log("files now on phone:\n" + run("shell", "ls", "-l", DEST, timeout=10))
    if "com.deskdash" in run("shell", "pm", "list", "packages", "com.deskdash", timeout=20):
        run("shell", "am", "force-stop", "com.deskdash", timeout=10)
        run("shell", "am", "start", "-n", "com.deskdash/.Main", timeout=20)
        log("push finished (opened in the Desk app)")
        return
    # closing the browser first makes it load the new files instead of a cached copy
    run("shell", "am", "force-stop", "com.android.browser", timeout=10)
    url = "file://" + DEST + "/index.html"
    # Open in the real Browser app. The plain "HTML viewer" has JavaScript switched off.
    out = run("shell", "am", "start", "-n", "com.android.browser/.BrowserActivity",
              "-a", "android.intent.action.VIEW", "-d", url, timeout=20)
    if "Error" in out:
        log("WARNING: could not start the Browser app; falling back to the HTML viewer (no JavaScript, page will look empty)")
        run("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url, "-t", "text/html", timeout=20)
    log("push finished")


def install_app():
    found = [p for p in (os.path.join(ROOT, "android", "build", "DeskDash.apk"), os.path.join(ROOT, "dist", "DeskDash.apk"))
             if os.path.exists(p)]
    if not found:
        sys.exit("DeskDash.apk not found in dist/ or android/build/ (build it with android/build.sh)")
    apk = max(found, key=os.path.getmtime)  # a fresh local build wins over the committed one
    log("app file: " + os.path.relpath(apk, ROOT))
    connect()
    step("installing the Desk app")
    out = run("install", "-r", apk, timeout=120)
    if "Success" not in out:
        log("WARNING: install said: " + out[-300:])
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:
            log("-> an older Desk app with another signature is installed; run: adb uninstall com.deskdash, then retry")
        sys.exit(1)
    run("shell", "am", "force-stop", "com.android.browser", timeout=10)
    run("shell", "settings", "put", "global", "stay_on_while_plugged_in", "3")
    push()
    log("Desk app installed. Tap Back on the phone to leave it; it also starts by itself after a reboot.")


def setup():
    step("1/5 finding the phone")
    connect()
    step("2/5 phone settings")
    run("shell", "settings", "put", "system", "screen_brightness_mode", "1")  # auto: uses the light sensor
    run("shell", "settings", "put", "global", "stay_on_while_plugged_in", "3")
    run("shell", "settings", "put", "global", "auto_time", "1")
    step("3/5 reading the phone's Wi-Fi address")
    m = re.search(r"wlan0\s+UP\s+(\d+\.\d+\.\d+\.\d+)", run("shell", "netcfg", timeout=15))
    if m:
        ip = m.group(1)
        open(IPFILE, "w").write(ip)
        step("4/5 switching adb to Wi-Fi (%s)" % ip)
        if "connected to" in adb("connect", ip + ":" + PORT, timeout=8):
            log("Wi-Fi adb already working: skipping 'tcpip' (running it again can freeze the USB link)")
        else:
            run("tcpip", PORT, timeout=15)
        for i in range(5):
            if "connected to" in adb("connect", ip + ":" + PORT, timeout=8):
                log("Wi-Fi adb ready. You can unplug USB after this step.")
                break
            log("not up yet, waiting 2s (try %d/5)" % (i + 1))
            time.sleep(2)
        else:
            log("WARNING: Wi-Fi adb did not come up. USB still works. Run: python3 tools/sync.py doctor")
    else:
        log("WARNING: phone has no Wi-Fi address (is Wi-Fi on?). Skipping Wi-Fi adb; USB still works.")
    step("5/5 first push")
    push()
    log("SETUP DONE in %.1fs" % (time.time() - T0))


def doctor():
    step("DOCTOR: checking everything")
    log("adb: " + (adb("version", timeout=10).splitlines() or ["?"])[0])
    log("python: " + sys.version.split()[0] + ", ImageMagick: " + ("yes" if shutil.which("convert") else "no"))
    for f in ("index.html", "data.js", "tasks.js", "todo.txt", "photo.jpg"):
        log("laptop file web/%-11s %s" % (f, "ok" if os.path.exists(os.path.join(WEB, f)) else "missing"))
    connect()
    lat = []
    for _ in range(3):
        t = time.time()
        run("shell", "echo", "ok", timeout=15)
        lat.append(time.time() - t)
    avg = sum(lat) / 3
    log("RESULT command latency avg %.2fs %s" % (avg, "(SLOW: weak Wi-Fi, bad cable or busy phone)" if avg > 1.5 else "(good)"))
    m = re.search(r"wlan0\s+(\w+)\s+(\d+\.\d+\.\d+\.\d+)", run("shell", "netcfg", timeout=15))
    log("RESULT phone Wi-Fi: " + (m.group(1) + " " + m.group(2) if m else "NOT connected"))
    if m:
        open(IPFILE, "w").write(m.group(2))
        try:
            socket.create_connection((m.group(2), int(PORT)), 3).close()
            log("RESULT port %s reachable from laptop: yes" % PORT)
        except OSError as e:
            log("RESULT port %s reachable from laptop: NO (%s). Run setup with USB." % (PORT, e))
        try:
            r = subprocess.run(["ping", "-c", "3", "-W", "2", m.group(2)], capture_output=True, text=True, timeout=15)
            loss, rtt = re.search(r"(\d+)% packet loss", r.stdout), re.search(r"= [\d.]+/([\d.]+)/", r.stdout)
            log("RESULT ping: loss %s%%, average %s ms" % (loss.group(1) if loss else "?", rtt.group(1) if rtt else "?"))
        except Exception as e:
            log("ping not available: %s" % e)
    tmp = os.path.join(ROOT, ".speedtest")
    open(tmp, "wb").write(os.urandom(1024 * 1024))
    run("shell", "mkdir", "-p", DEST)
    t = time.time()
    run("push", tmp, DEST + "/.speedtest", timeout=120)
    dt = max(time.time() - t, 0.01)
    log("RESULT transfer speed %.2f MB/s %s" % (1 / dt, "(SLOW)" if 1 / dt < 0.3 else "(ok)"))
    run("shell", "rm", DEST + "/.speedtest")
    os.remove(tmp)
    for ns, key in (("system", "screen_brightness_mode"), ("global", "stay_on_while_plugged_in"), ("global", "auto_time")):
        log("RESULT %s = %s" % (key, run("shell", "settings", "get", ns, key, timeout=10)))
    pk = [l for l in run("shell", "pm", "list", "packages", timeout=20).splitlines() if "browser" in l.lower()]
    log("RESULT browsers: " + (", ".join(pk) or "none found"))
    log("RESULT files on phone:\n" + run("shell", "ls", "-l", DEST, timeout=10))
    log("DOCTOR DONE in %.1fs. Full log: %s" % (time.time() - T0, LOG))


def fullscreen(mode):
    connect()
    run("shell", "settings", "put", "global", "policy_control",
        "null" if mode == "off" else "immersive.full=com.android.browser")
    log("fullscreen %s. Run 'push' to reopen the page. The first time, tap 'Got it' on the phone." % mode.upper())


def location_check(args):
    connect()
    step("is location working on the phone?")
    if args and args[0] == "on":
        run("shell", "settings", "put", "secure", "location_mode", "3")  # Android 4.4: high accuracy
        run("shell", "settings", "put", "secure", "location_providers_allowed", "+gps")
        run("shell", "settings", "put", "secure", "location_providers_allowed", "+network")
    mode = run("shell", "settings", "get", "secure", "location_mode", timeout=10).strip()
    prov = run("shell", "settings", "get", "secure", "location_providers_allowed", timeout=10).strip()
    log("RESULT location_mode = %s  (0 off, 1 GPS only, 2 battery saving, 3 high accuracy)" % mode)
    log("RESULT providers switched on: '%s'" % prov)
    if mode == "0" or not prov or prov == "null":
        log("PROBLEM: location is OFF on the phone. Run: python3 tools/sync.py location on")
    log("The Desk app shows its own location result in the bottom-right corner of the dashboard.")
    log("If it says location is blocked: on the phone, allow Location for 'Desk' in Phone Manager > Permissions.")


def image(src):
    dst = os.path.join(WEB, "photo.jpg")
    if shutil.which("convert"):
        subprocess.run(["convert", src + "[0]", "-auto-orient", "-resize", "1280x1280>", "-strip", "-quality", "90", dst], check=True)
    else:
        print("ImageMagick not found (sudo apt install imagemagick): copying the file as it is.")
        shutil.copy(src, dst)
    push()


def photos(folder):
    """Resize every picture in the folder, send them to the phone and list them in photos.js."""
    exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(exts))
    if not files:
        sys.exit("No pictures (.jpg .png .webp .gif) found in " + folder)
    connect()
    out = os.path.join(WEB, "photos")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    names = []
    for n, f in enumerate(files, 1):
        dst = os.path.join(out, "%03d.jpg" % n)
        if shutil.which("convert"):
            # full screen resolution, in colour (the phone can show it black-and-white), good quality
            subprocess.run(["convert", os.path.join(folder, f) + "[0]", "-auto-orient", "-resize", "1280x1280>",
                            "-strip", "-quality", "90", dst], check=True)
        else:
            dst = os.path.join(out, "%03d%s" % (n, os.path.splitext(f)[1].lower()))
            shutil.copy(os.path.join(folder, f), dst)
        names.append("photos/" + os.path.basename(dst))
        log("prepared %s -> %s" % (f, names[-1]))
    if not shutil.which("convert"):
        log("ImageMagick not found (sudo apt install imagemagick): big photos are sent as they are and may load slowly")
    open(os.path.join(WEB, "photos.js"), "w").write("var PHOTOS = " + json.dumps(names) + ";\n")
    run("shell", "rm", "-r", DEST + "/photos", timeout=30)
    run("shell", "mkdir", "-p", DEST + "/photos")
    for nm in names:
        run("push", os.path.join(WEB, nm), DEST + "/" + nm, timeout=90)
    log("%d photos sent" % len(names))
    push()


def todo(args):
    lines = [l for l in read_todo() if l.strip()]
    cmd = args[0] if args else "list"
    if cmd == "edit":
        subprocess.run([os.environ.get("EDITOR", "nano"), TODO])
        return push()
    if cmd == "add" and len(args) > 1:
        lines.append("[ ] " + " ".join(args[1:]))
    elif cmd in ("done", "undone", "rm") and len(args) > 1 and args[1].isdigit() and 0 < int(args[1]) <= len(lines):
        i = int(args[1]) - 1
        text = re.sub(r"^\[[ xX]\]\s*", "", lines[i].strip())
        if cmd == "rm":
            del lines[i]
        else:
            lines[i] = ("[x] " if cmd == "done" else "[ ] ") + text
    elif cmd != "list":
        sys.exit(__doc__)
    open(TODO, "w").write("\n".join(lines) + "\n")
    for n, l in enumerate(lines, 1):
        print(n, l)
    if cmd != "list":
        push()


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "setup": setup()
    elif a[0] == "doctor": doctor()
    elif a[0] == "push": push()
    elif a[0] == "app": install_app()
    elif a[0] == "tasks": make_tasks()
    elif a[0] == "fullscreen" and len(a) > 1: fullscreen(a[1])
    elif a[0] == "location": location_check(a[1:])
    elif a[0] == "image" and len(a) > 1: image(a[1])
    elif a[0] == "photos" and len(a) > 1: photos(os.path.expanduser(a[1]))
    elif a[0] == "todo": todo(a[1:])
    else: sys.exit(__doc__)
