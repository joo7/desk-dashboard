#!/usr/bin/env python3
"""Photo manager for the dashboard.  Run: python3 tools/photos_ui.py   (then use the page it opens)

The photos live on the phone, and only there. The page shows what the phone has. Pictures dropped on it are
resized and sent straight to the phone; hiding or deleting a photo acts on the phone. Nothing stays on this
laptop: its temporary files are removed when this stops.

It listens on this computer only, and refuses requests that come from other websites.
"""
import atexit, glob, http.server, json, os, queue, re, shutil, signal, subprocess, sys, tempfile, threading, time, urllib.parse, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync

HOST, PORT = "127.0.0.1", 8765
PAGE = os.path.join(HERE, "photos_ui.html")
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif")
MAX_UPLOAD = 100 * 1024 * 1024
LOOK_EVERY = 10                      # seconds between looks at the phone
NAME = re.compile(r"[A-Za-z0-9_-]+")
NOT_CONNECTED = "Your phone isn’t connected. Connect it, then try again."


class Refused(Exception):
    """A request we turn down, with a message for the person using the page."""


def picture_extension(name):
    ext = os.path.splitext(os.path.basename(name.replace("\\", "/")))[1].lower()
    return ext if ext in EXTS else None


def dropped_paths(uris):
    """Pictures named by a drag from an app that sends file addresses (VS Code, some file managers). A folder means the pictures in it."""
    out = []
    for uri in uris:
        parts = urllib.parse.urlsplit(uri) if isinstance(uri, str) else None
        if not parts or parts.scheme != "file" or parts.netloc not in ("", "localhost"):
            raise Refused("That didn’t come from a file on this computer. Save the picture first, then drop the file.")
        path = urllib.parse.unquote(parts.path)
        if os.path.isdir(path):
            out += [os.path.join(path, n) for n in sorted(os.listdir(path)) if picture_extension(n)]
        elif os.path.isfile(path):
            out.append(path)
        else:
            raise Refused("%s couldn’t be found." % os.path.basename(path))
    return out


def sort_photos(listed, files):
    """Split the phone's photos by the list: (shown, hidden), each as [{name, v}] where v changes when the file does."""
    mains = {f[:-4]: size for f, size in files.items() if sync.base_of(f) == f[:-4]}
    shown = [n[len("photos/"):-4] for n in listed if n.startswith("photos/") and n.endswith(".jpg")]
    shown = [b for b in shown if b in mains]
    entry = lambda b: {"name": b, "v": mains[b]}
    return [entry(b) for b in shown], [entry(b) for b in sorted(set(mains) - set(shown))]


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


class Phone:
    """Everything that changes the phone happens on this class's own thread, one job at a time."""

    def __init__(self, work):
        self.work = work
        self.lock = threading.Lock()
        self.jobs = queue.Queue()
        self.quiet = False
        self.state = {"checked": False, "connected": False, "shown": [], "hidden": [], "at": None}
        self.detail, self.working, self.serial = "", False, None
        self.notes, self.note_id = [], 0
        self.thumbs = threading.Semaphore(2)

    def report(self):
        with self.lock:
            busy = self.working or not self.jobs.empty()
            return dict(self.state, busy=busy, detail=self.detail, notes=list(self.notes))

    def note(self, text, bad=False):
        with self.lock:
            self.note_id += 1
            self.notes = (self.notes + [{"id": self.note_id, "text": text, "bad": bad}])[-30:]

    def require(self):
        with self.lock:
            if not self.state["connected"]:
                raise Refused(NOT_CONNECTED)

    def check_names(self, names):
        """Names come from the page, so they are never trusted: each must be a photo the phone has right now."""
        with self.lock:
            known = {p["name"] for p in self.state["shown"] + self.state["hidden"]}
        if not isinstance(names, list) or not names:
            raise Refused("No photos chosen.")
        for n in names:
            if not isinstance(n, str) or not NAME.fullmatch(n) or n not in known:
                raise Refused("That photo is no longer on your phone. Refresh the page.")

    def ask(self, kind, payload):
        self.require()
        self.jobs.put((kind, payload))

    def follow(self, msg):
        """Pick out of the sync tool's log what the person should see."""
        if msg.startswith("WARNING:") and "blurry" in msg:
            self.note(msg[len("WARNING: "):], True)

    def connect(self):
        self.quiet = True
        try:
            sync.connect()
            self.serial = sync.SER
        finally:
            self.quiet = False

    def look(self):
        """Read the phone. If it isn't there, say so, and keep showing what was last seen."""
        self.quiet = True
        try:
            self.connect()
            self.quiet = True
            sync.run("shell", "mkdir", "-p", sync.PHOTO_DIR)
            files = sync.phone_sizes(sync.PHOTO_DIR)
            listed = (sync.read_phone_list() or ([], {}))[0]
        except SystemExit:
            with self.lock:
                self.state = dict(self.state, checked=True, connected=False)
            return
        finally:
            self.quiet = False
        shown, hidden = sort_photos(listed, files)
        with self.lock:
            self.state = {"checked": True, "connected": True, "shown": shown, "hidden": hidden, "at": time.strftime("%H:%M")}

    def fresh(self):
        """Today's list and files from the phone, leaving out any listed photo whose file has gone."""
        names, info = sync.read_phone_list() or ([], {})
        files = sync.phone_sizes(sync.PHOTO_DIR)
        return [n for n in names if n[len("photos/"):] in files], info, files

    def do(self, kind, payload):
        self.connect()
        if kind == "add":
            self.add(*payload)
            return
        names, info, files = self.fresh()
        keys = ["photos/" + b + ".jpg" for b in payload]
        if kind in ("hide", "delete") and not [n for n in names if n not in keys]:
            self.note("Keep at least one photo showing on your phone.", True)
            return
        if kind == "show":
            self.detail = "Showing " + plural(len(payload), "photo")
            sync.show_pictures(payload, names, info, files)
        elif kind == "hide":
            self.detail = "Hiding " + plural(len(payload), "photo")
            sync.save_phone_list([n for n in names if n not in keys], info)
        elif kind == "delete":
            self.detail = "Deleting " + plural(len(payload), "photo")
            for key in keys:                                  # off the dashboard first, so it never asks for a missing file
                info.pop(key, None)
            sync.save_phone_list([n for n in names if n not in keys], info)
            for b in payload:
                for s in sync.SUFFIXES:
                    sync.run("shell", "rm", sync.PHOTO_DIR + "/" + b + s)
            left = [f for f in sync.phone_sizes(sync.PHOTO_DIR) if sync.base_of(f) in payload]
            if left:
                self.note("Some files couldn’t be deleted from your phone: " + ", ".join(left[:4]), True)

    def add(self, tmp, original):
        label = os.path.basename(original)
        self.detail = "Adding " + label
        try:
            if subprocess.run(["identify", "-ping", tmp + "[0]"], capture_output=True, timeout=60).returncode != 0:
                self.note("%s couldn’t be opened as a picture." % label, True)
                return
            name, what = sync.add_picture(tmp, label)
        except subprocess.SubprocessError:
            self.note("%s couldn’t be opened as a picture." % label, True)
            return
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if what == "same":
            self.note("%s is already showing on your phone." % label)
            return
        self.note(("%s added. Your phone will show it within a few seconds." if what == "added"
                   else "%s was hidden, so it’s showing again.") % label)

    def run(self):
        original = sync.log

        def log(msg):
            if not self.quiet:
                original(msg)
                self.follow(msg)
        sync.log = log
        next_look = 0
        while True:
            try:
                job = self.jobs.get(timeout=0.5)
            except queue.Empty:
                job = None
            try:
                self.working = True
                if job:
                    self.do(*job)
                    self.look()
                    next_look = time.time() + LOOK_EVERY
                elif time.time() >= next_look:
                    self.look()
                    next_look = time.time() + LOOK_EVERY
            except SystemExit as e:                  # the sync tool stops with a plain message, e.g. phone not found
                self.note(str(e.code).split("\n")[0], True)
                self.look()
            except Exception as e:                   # one failure must not stop everything after it
                original("photo manager: %r" % e)
                self.note("Something went wrong talking to your phone. Details are in sync.log.", True)
            finally:
                self.working = False
                self.detail = ""
                if job and job[0] == "add" and os.path.exists(job[1][0]):
                    os.remove(job[1][0])

    def thumbnail(self, base, version):
        with self.lock:
            known = {p["name"] for p in self.state["shown"] + self.state["hidden"]}
        if not NAME.fullmatch(base) or base not in known:
            raise Refused("That photo is no longer on your phone.")
        version = re.sub(r"\D", "", version)
        dst = os.path.join(self.work, "thumb-%s-%s.jpg" % (base, version))
        with self.thumbs:
            if not os.path.exists(dst):
                pulled = dst + ".full.jpg"
                # Not through sync.run: this is on a web request's thread, and only reads.
                subprocess.run(["adb", "-s", str(self.serial), "pull", sync.PHOTO_DIR + "/" + base + ".jpg", pulled],
                               capture_output=True, timeout=60, check=True)
                try:
                    subprocess.run(["convert", pulled, "-thumbnail", "520x520", "-quality", "82", dst + ".tmp.jpg"],
                                   capture_output=True, timeout=60, check=True)
                    os.replace(dst + ".tmp.jpg", dst)
                finally:
                    os.remove(pulled)
        return dst


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self, code, body, kind="application/json", cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.reply(code, json.dumps(obj).encode())

    def allowed_host(self):
        """A website can't talk to this: its name won't match here, even if it points itself at this computer."""
        port = self.server.server_address[1]
        return self.headers.get("Host") in ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def do_GET(self):
        if not self.allowed_host():
            self.close_connection = True
            return self.json({"error": "Not allowed."}, 403)
        url = urllib.parse.urlsplit(self.path)
        try:
            if url.path == "/":
                with open(PAGE, "rb") as f:
                    return self.reply(200, f.read(), "text/html; charset=utf-8")
            if url.path == "/api/state":
                return self.json(PHONE.report())
            if url.path == "/thumb":
                q = urllib.parse.parse_qs(url.query)
                with open(PHONE.thumbnail(q.get("name", [""])[0], q.get("v", [""])[0]), "rb") as f:
                    return self.reply(200, f.read(), "image/jpeg")   # no-store: the browser keeps no copy on disk
            m = re.fullmatch(r"/fonts/(Hind-(?:Regular|Medium)\.ttf)", url.path)
            if m:
                with open(os.path.join(sync.WEB, "fonts", m.group(1)), "rb") as f:
                    return self.reply(200, f.read(), "font/ttf", "private, max-age=86400")
            self.json({"error": "Not found."}, 404)
        except Refused as e:
            self.json({"error": str(e)}, 404)
        except (OSError, subprocess.SubprocessError):
            self.json({"error": "Couldn’t read that from your phone."}, 500)

    def do_POST(self):
        # A custom header can't be sent by another website without asking first, and this server never says yes.
        if not self.allowed_host() or self.headers.get("X-Desk-Photos") != "1":
            self.close_connection = True
            return self.json({"error": "Not allowed."}, 403)
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.close_connection = True
            return self.json({"error": "Not allowed."}, 400)
        try:
            if self.path == "/api/upload":
                return self.upload(size)
            if size > 1 << 20:
                self.close_connection = True
                raise Refused("Too much data.")
            data = json.loads(self.rfile.read(size) or b"{}")
            if self.path == "/api/add-files":
                return self.add_files(data.get("uris"))
            m = re.fullmatch(r"/api/(show|hide|delete)", self.path)
            if not m:
                return self.json({"error": "Not found."}, 404)
            names = data.get("names")
            PHONE.check_names(names)
            PHONE.ask(m.group(1), names)
            self.json({"queued": len(names)})
        except Refused as e:
            self.json({"error": str(e)}, 400)
        except ValueError:
            self.json({"error": "That request wasn’t understood."}, 400)

    def temp_for(self, name):
        fd, tmp = tempfile.mkstemp(prefix="in-", suffix=picture_extension(name), dir=PHONE.work)
        return fd, tmp

    def upload(self, size):
        original = os.path.basename(urllib.parse.unquote(self.headers.get("X-File-Name", "")).replace("\\", "/"))
        try:
            if size > MAX_UPLOAD or size <= 0:
                raise Refused("%s is too large (the limit is 100 MB)." % original)
            if not picture_extension(original):
                raise Refused("%s isn’t a picture this can use (JPG, PNG, WebP, GIF or HEIC)." % original)
            PHONE.require()
        except Refused:
            self.close_connection = True      # the body is never read
            raise
        fd, tmp = self.temp_for(original)
        with os.fdopen(fd, "wb") as out:
            left = size
            while left:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    os.remove(tmp)
                    self.close_connection = True
                    raise Refused("%s didn’t finish uploading." % original)
                out.write(chunk)
                left -= len(chunk)
        PHONE.ask("add", (tmp, original))
        self.json({"queued": 1})

    def add_files(self, uris):
        PHONE.require()
        if not isinstance(uris, list) or not uris:
            raise Refused("No pictures found in what you dropped.")
        queued, problems = 0, []
        for path in dropped_paths(uris):
            name = os.path.basename(path)
            try:
                if not picture_extension(name):
                    raise Refused("%s isn’t a picture this can use (JPG, PNG, WebP, GIF or HEIC)." % name)
                if os.path.getsize(path) > MAX_UPLOAD:
                    raise Refused("%s is too large (the limit is 100 MB)." % name)
                fd, tmp = self.temp_for(name)
                os.close(fd)
                shutil.copy(path, tmp)
                PHONE.ask("add", (tmp, name))
                queued += 1
            except Refused as e:
                problems.append(str(e))
            except OSError:
                problems.append("%s couldn’t be read." % name)
        self.json({"queued": queued, "problems": problems})


PHONE = None


def main():
    global PHONE
    if not shutil.which("convert"):
        sys.exit("ImageMagick is needed: sudo apt install imagemagick")
    url = "http://%s:%d/" % (HOST, PORT)
    try:
        server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        print("The photo manager is already running: " + url)
        webbrowser.open(url)
        return
    # No copies of the phone's photos stay on this laptop. Holding the port means no other copy of this is running,
    # so anything here was left by a crash or power cut. Closing the terminal counts as a normal stop.
    for old in glob.glob(os.path.join(tempfile.gettempdir(), "desk-photos-*")):
        shutil.rmtree(old, True)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *a: sys.exit(0))
    work = tempfile.mkdtemp(prefix="desk-photos-")
    atexit.register(shutil.rmtree, work, True)
    PHONE = Phone(work)
    threading.Thread(target=PHONE.run, daemon=True).start()
    print("Photo manager: " + url + "   (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
