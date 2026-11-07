#!/usr/bin/env python3
"""Laptop helper for the phone dashboard.  Run: python3 tools/sync.py <command>

  setup                  one-time: auto brightness, stay awake, Wi-Fi adb, first push (phone on USB)
  app                    install the Desk app (DeskDash.apk): full screen, starts on boot; then push
  doctor                 run every check and show timings (use this when something is slow)
  push                   send everything to the phone and open it (USB or Wi-Fi)
  pick <serial>          choose which device is the dashboard phone (only needed with several attached)
  image <file>           show this one picture instead of the photo set (resized if ImageMagick exists) and push
                         (the photo set stays on the phone: show it again from the photo page)
  photos <folder>        add the pictures in a folder to the phone; never removes any
                         (to see, hide, delete or drop photos, use the page instead: python3 tools/photos_ui.py)
  todo list|add "text"|done N|undone N|rm N|edit     read or change the phone's to-do list
  tasks                  just rebuild tasks.js
  (weather, air quality, sunrise/sunset and location are handled on the phone; settings are in web/data.js)
  fullscreen on|off      hide the phone's status and navigation bars in the Browser app
  location [on]          check the phone's location service ('on' switches it on, GPS + Wi-Fi)

Paths: the page lives in web/, the app in dist/DeskDash.apk (or android/build/ after android/build.sh).
Every adb call is timed and written to sync.log in the repo folder (not committed).
"""
import colorsys, filecmp, json, os, re, shutil, socket, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo folder
WEB = os.path.join(ROOT, "web")                                       # everything sent to the phone
DEST, PORT = "/sdcard/dash", "5555"
TODO, IPFILE = os.path.join(WEB, "todo.txt"), os.path.join(ROOT, ".phone_ip")
SERIALFILE, OPSFILE = os.path.join(ROOT, ".phone_serial"), os.path.join(ROOT, ".todo_ops.json")
SRGB = ("/usr/share/color/icc/colord/sRGB.icc", "/usr/share/color/icc/ghostscript/srgb.icc")
PHOTO_DIR = DEST + "/photos"                                          # the phone is the only home of the photos
PHOTO_JS = DEST + "/photos.js"                                        # which of them the dashboard shows, in order
SUFFIXES = (".jpg", ".bw.jpg", ".blur.jpg", ".bw.blur.jpg")           # the files on the phone for one picture
PHOTO_FILE = re.compile(r"([A-Za-z0-9_-]+?)(\.bw\.blur|\.bw|\.blur)?\.jpg")
STATE = DEST + "/todo-state.json"                                     # the phone's to-do list, written by the page
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


def saved_serial():
    return open(SERIALFILE).read().strip() if os.path.exists(SERIALFILE) else ""


def connect():
    """Find the dashboard phone, over Wi-Fi if possible (the USB link keeps freezing), and never any other device."""
    global SER
    d = devices()
    if os.path.exists(IPFILE) and not any(":" in s for s in d):
        log("trying Wi-Fi at " + open(IPFILE).read().strip())
        adb("connect", open(IPFILE).read().strip() + ":" + PORT, timeout=8)
        d = devices()
    if not d:
        sys.exit("Phone not found. Plug in USB (debugging on), or run: python3 tools/sync.py setup")
    found = {}                                     # hardware serial -> first working adb address (Wi-Fi sorted first)
    for s in sorted(d, key=lambda x: ":" not in x):
        SER = s
        if "ok" not in run("shell", "echo", "ok", timeout=6):
            log("%s is listed but not answering, trying the next one" % s)
            continue
        found.setdefault(run("shell", "getprop", "ro.serialno", timeout=6).strip() or s, s)
    SER = None
    if not found:
        sys.exit("Phone is listed but frozen. Unplug USB for 5s and replug (or toggle USB debugging), then retry.")
    want = saved_serial()
    if want and want not in found:
        sys.exit("The dashboard phone (%s) is not connected. Attached: %s\n"
                 "If you replaced the phone, run: python3 tools/sync.py pick <serial>" % (want, ", ".join(sorted(found))))
    if not want:
        if len(found) > 1:
            sys.exit("Several devices attached: %s\nChoose the dashboard phone: python3 tools/sync.py pick <serial>"
                     % ", ".join(sorted(found)))
        want = next(iter(found))
        open(SERIALFILE, "w").write(want)
        log("dashboard phone is now %s (saved in .phone_serial)" % want)
    SER = found[want]
    log("using %s (%s)" % (SER, "Wi-Fi" if ":" in SER else "USB"))


def run(*a, timeout=30):
    return adb("-s", SER, *a, timeout=timeout)


def parse_todo(lines):
    """Turn '[x] text' lines into items."""
    items = []
    for line in lines:
        line = line.strip()
        if line:
            items.append({"t": re.sub(r"^\[[ xX]\]\s*", "", line), "done": line.lower().startswith("[x]")})
    return items


def format_todo(items):
    return "".join("[%s] %s\n" % ("x" if i["done"] else " ", i["t"]) for i in items)


def read_todo():
    return parse_todo(open(TODO, encoding="utf-8").read().splitlines()) if os.path.exists(TODO) else []


def write_todo(items):
    with open(TODO, "w", encoding="utf-8") as f:
        f.write(format_todo(items))


def apply_ops(items, ops):
    """What the page does with TODO_OPS (web/index.html, applyOps)."""
    items = [dict(i) for i in items]
    for o in ops:
        hit = next((i for i in items if i["t"] == o["t"]), None)
        if o["op"] == "add" and not hit:
            items.append({"t": o["t"], "done": bool(o.get("done"))})
        elif o["op"] in ("done", "undone") and hit:
            hit["done"] = o["op"] == "done"
        elif o["op"] == "rm" and hit:
            items.remove(hit)
    return items


def diff_ops(old, new, first_id):
    """The numbered changes that turn list old into list new."""
    ops, was = [], {i["t"]: i for i in old}
    keep = {i["t"] for i in new}
    for i in old:
        if i["t"] not in keep:
            ops.append({"op": "rm", "t": i["t"]})
    for i in new:
        if i["t"] not in was:
            ops.append({"op": "add", "t": i["t"], "done": i["done"]})
        elif was[i["t"]]["done"] != i["done"]:
            ops.append({"op": "done" if i["done"] else "undone", "t": i["t"]})
    for n, o in enumerate(ops):
        o["id"] = first_id + n
    return ops


def pending_ops(seq):
    """Laptop changes the phone hasn't applied yet."""
    if not os.path.exists(OPSFILE):
        return []
    return [o for o in json.load(open(OPSFILE, encoding="utf-8")) if o["id"] > seq]


def phone_state():
    """The phone's to-do list as (items, seq), or None if it has not written one yet."""
    tmp = OPSFILE + ".pull"
    run("pull", STATE, tmp, timeout=30)
    if not os.path.exists(tmp):
        return None
    try:
        with open(tmp, encoding="utf-8") as f:
            st = json.load(f)
        return st.get("items", []), st.get("seq", 0)
    except ValueError:
        log("WARNING: could not read the phone's to-do file")
        return None
    finally:
        os.remove(tmp)


def sync_todo():
    """Read the list from the phone, include unapplied laptop changes, and mirror it to todo.txt.
    Returns (items, pending changes, next change id). Without a phone list, todo.txt is the starting point."""
    st = phone_state()
    items, seq = st if st else (read_todo(), 0)
    pending = pending_ops(seq)
    items = apply_ops(items, pending)
    write_todo(items)
    return items, pending, max([seq] + [o["id"] for o in pending]) + 1


def make_tasks(pending=None):
    """tasks.js: the list that seeds a brand-new phone, and the changes waiting to be applied."""
    if pending is None:
        pending = json.load(open(OPSFILE, encoding="utf-8")) if os.path.exists(OPSFILE) else []
    items = read_todo()
    with open(os.path.join(WEB, "tasks.js"), "w", encoding="utf-8") as f:
        f.write("var TODO = " + json.dumps(items, ensure_ascii=False) + ";\n")
        f.write("var TODO_OPS = " + json.dumps(pending, ensure_ascii=False) + ";\n")
    log("tasks.js rebuilt (%d items, %d changes for the phone)" % (len(items), len(pending)))


def check_page():
    """A script error leaves the phone showing a broken page, so look for one right after sending."""
    time.sleep(4)
    errors = [l for l in run("logcat", "-d", "-s", "DeskDash:I", timeout=15).splitlines() if "Uncaught" in l or "JS error" in l]
    if errors:
        log("ERROR: the page has a script error, so the dashboard is broken on the phone:\n" + "\n".join(errors[:5]))
    else:
        log("page loaded with no script errors")


def open_app():
    """Restart the Desk app so it reads what was just sent, and check the page came up."""
    run("logcat", "-c", timeout=10)
    run("shell", "am", "force-stop", "com.deskdash", timeout=10)
    run("shell", "am", "start", "-n", "com.deskdash/.Main", timeout=20)
    check_page()


def push(keep_phone_list=True):
    step("sending files")
    connect()
    if keep_phone_list:     # the phone decides which photos are shown: this laptop's copy of the list may be out of date
        phone = read_phone_list()
        if phone:
            write_photos_js(*phone)
    make_tasks(sync_todo()[1])
    if not os.path.exists(os.path.join(WEB, "data.js")):
        shutil.copy(os.path.join(WEB, "data.example.js"), os.path.join(WEB, "data.js"))
        log("created web/data.js from data.example.js: edit it for your location")
    if not os.path.exists(os.path.join(WEB, "photos.js")):
        open(os.path.join(WEB, "photos.js"), "w").write("var PHOTOS = [];\n")
    run("shell", "mkdir", "-p", DEST)
    for name in ("index.html", "data.js", "tasks.js", "photos.js", "holidays.js", "photo.jpg", "photo.bw.jpg"):
        path = os.path.join(WEB, name)
        if os.path.exists(path):
            log("pushing %s (%d KB)" % (name, os.path.getsize(path) // 1024))
            run("push", path, DEST + "/" + name, timeout=90)
    run("shell", "mkdir", "-p", DEST + "/fonts")
    sizes = phone_sizes(DEST + "/fonts")
    for name in sorted(os.listdir(os.path.join(WEB, "fonts"))):
        path = os.path.join(WEB, "fonts", name)
        if name.endswith(".ttf") and sizes.get(name) != str(os.path.getsize(path)):
            run("push", path, DEST + "/fonts/" + name, timeout=90)
    log("files now on phone:\n" + run("shell", "ls", "-l", DEST, timeout=10))
    if "com.deskdash" in run("shell", "pm", "list", "packages", "com.deskdash", timeout=20):
        open_app()
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


def prepare(src, dst):
    """Make a sharp screen-sized JPEG and a grey copy (dst.bw.jpg). A CSS grey filter would blur the photo on the phone."""
    # Phone cameras save in wider colour (Display P3); converting keeps the colours right, stripping alone would wash them out.
    srgb = next((p for p in SRGB if os.path.exists(p)), None)
    base = ["convert", src + "[0]", "-auto-orient"] + (["-profile", srgb] if srgb else []) + [
            "-filter", "Lanczos", "-resize", "1280x1280>", "-strip",
            "-unsharp", "0x0.6+0.6+0.01", "-sampling-factor", "1x1", "-quality", "93"]
    subprocess.run(base + [dst], check=True)
    subprocess.run(base + ["-colorspace", "Gray", dst[:-4] + ".bw.jpg"], check=True)
    w, h = subprocess.run(["identify", "-format", "%w %h", dst], capture_output=True, text=True, check=True).stdout.split()
    if max(int(w), int(h)) < 720:
        log("WARNING: %s is only %sx%s pixels and will look blurry. Use a larger copy if you have one." % (os.path.basename(src), w, h))


def blur_copy(path):
    """Make the small blurred, darkened backdrop (x.blur.jpg) for one prepared picture. Blurring a full photo live freezes the phone."""
    subprocess.run(["convert", path, "-resize", "200x200", "-virtual-pixel", "edge", "-blur", "0x4.5", "-evaluate", "multiply", "0.62",
                    "-strip", "-quality", "85", path[:-4] + ".blur.jpg"], check=True)


def pick_hue(hist):
    """Choose the photo's colour from [(pixel count, r, g, b)]: common and colourful wins. Returns (hue, saturation %)."""
    total = sum(h[0] for h in hist) or 1
    best = (0, 200, 0)
    for n, r, g, b in hist:
        hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if n / total < 0.01 or not 0.08 < light < 0.95:   # specks, near-black and near-white say little
            continue
        score = (n / total) ** 0.5 * (sat + 0.02) ** 1.5
        if score > best[0]:
            best = (score, round(hue * 360), round(sat * 100))
    return best[1], best[2]


def photo_info(path):
    """What the page needs to colour itself around a photo: its shape and main colour."""
    out = subprocess.run(["convert", path, "-format", "%w %h\n", "-write", "info:-", "-resize", "100x100!", "-colors", "8", "-depth", "8",
                          "-format", "%c", "histogram:info:-"], capture_output=True, text=True, check=True).stdout
    lines = out.splitlines()
    w, h = lines[0].split()
    hist = [(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            for m in (re.search(r"(\d+): \((\d+),(\d+),(\d+)", l) for l in lines[1:]) if m]
    hue, sat = pick_hue(hist)
    return {"w": int(w), "h": int(h), "hue": hue, "sat": sat}


def write_photos_js(names, info):
    with open(os.path.join(WEB, "photos.js"), "w") as f:
        f.write("var PHOTOS = " + json.dumps(names) + ";\nvar PHOTO_INFO = " + json.dumps(info) + ";\n")


def phone_sizes(folder):
    """File sizes on the phone, so unchanged files aren't sent again."""
    listing = run("shell", "ls", "-l", folder, timeout=20)
    return {p[-1]: p[-4] for p in (l.split() for l in listing.splitlines()) if len(p) >= 6 and "." in p[-1]}


def image(src):
    dst = os.path.join(WEB, "photo.jpg")
    if shutil.which("convert"):
        prepare(src, dst)
    else:
        print("ImageMagick not found (sudo apt install imagemagick): copying the file as it is.")
        shutil.copy(src, dst)
    # a photo set would take priority over this picture; take it out of rotation (files stay, re-run 'photos' to restore)
    write_photos_js([], {"photo.jpg": photo_info(dst)} if shutil.which("convert") else {})
    push(keep_phone_list=False)


def photo_name(src):
    """Phone file name for a picture: plain characters only, and the same every time so unchanged photos are skipped."""
    return (re.sub(r"[^A-Za-z0-9_-]", "_", src).lstrip("-_") or "photo") + ".jpg"


def base_of(phone_file):
    """IMG_1_jpg for any of IMG_1_jpg.jpg, .bw.jpg, .blur.jpg and .bw.blur.jpg; None for anything else."""
    m = PHOTO_FILE.fullmatch(phone_file)
    return m.group(1) if m else None


def parse_photo_list(text):
    """(names, info) from the text of photos.js; None if it can't be read, so a bad read never replaces the real list."""
    m = re.search(r"var PHOTOS = (\[.*?\]);", text)
    i = re.search(r"var PHOTO_INFO = (\{.*\});", text)
    try:
        return json.loads(m.group(1)), json.loads(i.group(1)) if i else {}
    except (AttributeError, ValueError):
        return None


def read_phone_list():
    """The phone's list of shown photos as (names, info), or None if it has never had one. Stops if it can't be read."""
    out = run("shell", "cat", PHOTO_JS, timeout=20)
    if "No such file" in out:
        return None
    parsed = parse_photo_list(out)
    if parsed is None:
        sys.exit("Couldn't read the photo list from the phone. Check the connection and try again.")
    return parsed


def save_phone_list(names, info):
    write_photos_js(names, info)
    # Swapped in whole: the running dashboard reads this file every few seconds and must never see half of it.
    run("push", os.path.join(WEB, "photos.js"), PHOTO_JS + ".new", timeout=30)
    run("shell", "mv", PHOTO_JS + ".new", PHOTO_JS, timeout=20)
    if (read_phone_list() or ([], {}))[0] != names:
        sys.exit("The photo list didn't reach the phone. Check the connection and try again.")


def make_copies(src, folder):
    """Everything the phone needs for one picture, as pic.jpg and friends in folder. Returns its colour info."""
    main = os.path.join(folder, "pic.jpg")
    prepare(src, main)
    blur_copy(main)
    blur_copy(main[:-4] + ".bw.jpg")
    return photo_info(main)


def send_copies(folder, base):
    """Send one picture's files, the main one last, so a photo only counts as there once it's all there."""
    for s in reversed(SUFFIXES):
        path = os.path.join(folder, "pic" + s)
        name = base + s
        run("push", path, PHOTO_DIR + "/" + name, timeout=90)
        if phone_sizes(PHOTO_DIR).get(name) != str(os.path.getsize(path)):
            sys.exit("%s didn't reach the phone. Check the connection and try again." % name)


def same_on_phone(main, files):
    """The phone picture identical to this prepared file, if any. Sizes pick the candidates; only the bytes decide."""
    size = str(os.path.getsize(main))
    with tempfile.TemporaryDirectory() as tmp:
        for name, s in files.items():
            if s == size and base_of(name) == name[:-4]:
                copy = os.path.join(tmp, "phone.jpg")
                run("pull", PHOTO_DIR + "/" + name, copy, timeout=60)
                if os.path.exists(copy) and filecmp.cmp(main, copy, shallow=False):
                    return name[:-4]
    return None


def add_picture(src, original):
    """Put one picture on the phone and on the dashboard. Returns (name, 'added', 'same' or 'restored')."""
    names, info = read_phone_list() or ([], {})
    run("shell", "mkdir", "-p", PHOTO_DIR)
    files = phone_sizes(PHOTO_DIR)
    with tempfile.TemporaryDirectory() as work:
        details = make_copies(src, work)
        same = same_on_phone(os.path.join(work, "pic.jpg"), files)
        if same:
            if "photos/" + same + ".jpg" in names:
                return same, "same"
            show_pictures([same], names, info, files)
            return same, "restored"
        base = stem = photo_name(os.path.basename(original))[:-4]
        n = 2
        while any(base_of(f) == base for f in files):
            base, n = "%s-%d" % (stem, n), n + 1
        send_copies(work, base)
    key = "photos/" + base + ".jpg"
    info[key] = details
    save_phone_list(names + [key], info)
    return base, "added"


def show_pictures(bases, names, info, files):
    """Put hidden photos back on the dashboard, making any of their files that are missing (photos from an older version)."""
    for base in bases:
        key = "photos/" + base + ".jpg"
        missing = not all(base + s in files for s in SUFFIXES)
        if missing or key not in info:
            with tempfile.TemporaryDirectory() as work:
                copy = os.path.join(work, "phone.jpg")
                run("pull", PHOTO_DIR + "/" + base + ".jpg", copy, timeout=60)
                if not os.path.exists(copy):
                    sys.exit("%s couldn't be read from the phone." % base)
                info[key] = make_copies(copy, work)
                if missing:
                    for s in SUFFIXES[1:]:
                        run("push", os.path.join(work, "pic" + s), PHOTO_DIR + "/" + base + s, timeout=90)
        if key not in names:
            names = names + [key]
    save_phone_list(names, info)


def photos(folder):
    """Add every picture in a folder to the phone. Nothing is removed, and nothing is kept on this laptop."""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        sys.exit("Folder not found: " + folder)
    if not shutil.which("convert"):
        sys.exit("ImageMagick is needed for photos: sudo apt install imagemagick")
    exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif")
    files = [f for f in sorted(os.listdir(folder)) if f.lower().endswith(exts)]
    if not files:
        sys.exit("No pictures (.jpg .png .webp .gif .heic) found in " + folder)
    connect()
    for f in files:
        name, what = add_picture(os.path.join(folder, f), f)
        log("%s: %s" % (f, what))


def todo(args):
    cmd = args[0] if args else "list"
    if cmd == "list":
        try:
            connect()
            items = sync_todo()[0]
        except SystemExit as e:
            print("%s\nShowing the last copy from todo.txt:" % e)
            items = read_todo()
    else:
        connect()
        items, pending, next_id = sync_todo()
        new = [dict(i) for i in items]
        if cmd == "edit":
            subprocess.run([os.environ.get("EDITOR", "nano"), TODO])
            new = read_todo()
        elif cmd == "add" and len(args) > 1:
            text = " ".join(args[1:]).strip()
            if not any(i["t"] == text for i in new):
                new.append({"t": text, "done": False})
        elif cmd in ("done", "undone", "rm") and len(args) > 1 and args[1].isdigit() and 0 < int(args[1]) <= len(new):
            i = int(args[1]) - 1
            if cmd == "rm":
                del new[i]
            else:
                new[i]["done"] = cmd == "done"
        else:
            sys.exit(__doc__)
        ops = pending + diff_ops(items, new, next_id)
        with open(OPSFILE, "w", encoding="utf-8") as f:
            json.dump(ops, f, ensure_ascii=False)
        write_todo(new)
        items = new
    for n, i in enumerate(items, 1):
        print(n, "[%s]" % ("x" if i["done"] else " "), i["t"])
    if cmd != "list":
        push()


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "setup": setup()
    elif a[0] == "pick" and len(a) > 1: open(SERIALFILE, "w").write(a[1]); print("dashboard phone is now " + a[1])
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
