# Desk dashboard

Turns an old Android phone (built for an Honor Holly, Android 4.4) into an always-on desk display with six pages:

- **Home**: clock, weather, the next hours and a whole photo, with air quality and sunrise/sunset below. Scroll down for your to-do list
- **Photos**: full-screen slideshow
- **This week**: today in detail, then six day cards
- **Weather**: as many cities as you like. Tap **+ Add city** to search; what you type goes to Open-Meteo's search
- **Calendar**: month view with Indian holidays and festivals, the next ones listed, and optional events from `web/data.js`
- **Focus**: timer that beeps when it ends

A **Habits** page is also built in. It's off by default; set `habits: true` in `web/data.js` to bring it back (saved habits are kept).

Weather refreshes every 15 minutes, and retries every 5 if the connection fails.

## Holidays

Dates are in `web/holidays.js`, from the Government of India DoPT lists, and cover 2026 and 2027. Each year's list is usually
published around July of the year before: add the new dates to that file, then run `python3 tools/sync.py push`.
Eid, Bakrid, Muharram and Milad-un-Nabi depend on the moon and can move by a day.

Everything runs **on the phone**. The laptop only sends changes over `adb`.

## Layout

```
desk-dashboard/
├── web/            the dashboard, copied to /sdcard/dash on the phone
│   ├── index.html  page (plain ES5 JavaScript so it runs on Android 4.4)
│   ├── holidays.js  holiday dates for the calendar
│   ├── data.example.js  template for data.js, your settings: location, clock, photo timing, night hours, extra tiles
│   └── photo.jpg   default picture
├── tools/
│   ├── sync.py     laptop helper: push files, install the app, send photos, diagnostics
│   └── test_sync.py tests for the to-do logic
├── android/        source of the Desk app (Java; no Gradle or Android Studio needed)
│   ├── AndroidManifest.xml
│   ├── build.sh
│   ├── res/
│   └── src/com/deskdash/
└── dist/
    └── DeskDash.apk   ready-built app
```

Files that are generated or personal (`web/data.js`, `web/todo.txt`, `web/photos/`, `web/tasks.js`, `web/photos.js`,
`sync.log`, `.phone_ip`, `.phone_serial`, `.todo_ops.json`), downloaded build libraries (`android/libs/`)
and the app signing key are listed in `.gitignore`.

## Quick start

On the phone, turn on USB debugging (Settings > Developer options) and join the same Wi-Fi as the laptop. Then:

```bash
sudo apt install adb imagemagick
python3 tools/sync.py setup                 # first time, phone on USB: settings, Wi-Fi adb, first push
python3 tools/sync.py app                   # install or update the Desk app
```

The first push creates `web/data.js` from the template: edit it for your location, then push again.
The first device found is saved as the dashboard phone in `.phone_serial`, and the tool won't touch any other device.
With several devices attached, choose one: `python3 tools/sync.py pick <serial>`.

## Everyday commands

```bash
python3 tools/sync.py push                  # send changes after editing anything in web/
python3 tools/sync.py photos                # make the phone's photos match the photos/ folder (see Adding photos)
python3 tools/sync.py image x.jpg           # show one picture instead of the photo set (run photos again to go back)
python3 tools/sync.py todo list             # the phone's list. Also: add "text", done N, undone N, rm N, edit
python3 tools/sync.py doctor                # check the connection when something is slow
python3 tools/sync.py location on           # switch on the phone's location setting
python3 tools/test_sync.py                  # run the tests
```

## On the phone

- **Swipe sideways**: change page. The dots and gear show when you touch the screen and fade after a few seconds
- **Drag up or down**: scroll the page. On Home, this reaches the tiles and to-do list
- **Tap a photo**: next photo (on the Photos page, tap the left side to go back)
- **Gear icon**: how often the photo changes, the style (Modern dark, E-ink, or Light with dark at night) and photo colour
- **+ Add**: add a to-do item or habit. **✕**: delete one. **Tap** an item to tick it
- **Turn the phone**: the layout follows, in portrait or landscape (the phone's rotation lock is respected)
- **Tap the status line**: read a long message in full

## Adding photos

1. Copy pictures into `photos/` in this repo (or delete the ones you no longer want). It isn't committed to git.
2. Run `python3 tools/sync.py photos`.

Only new or changed pictures are processed and sent. Pictures you removed from the folder are removed from the phone.

## Photo quality

Photos are shown whole on a blurred copy of themselves, so nothing is cropped. A photo can only look as good as its
file: `photos` warns about small pictures, so send the original rather than a thumbnail or WhatsApp copy.
The screen is 1280 x 720, so files are sized to 1280 px, and wide-colour phone photos (Display P3) are converted to sRGB. Never add a CSS filter to the sharp photo: this WebView draws
filtered content at half resolution, which is why black & white uses separate grey files made by `sync.py`.

## The to-do list

The phone owns the list. It keeps it in the app's storage and mirrors it to `/sdcard/dash/todo-state.json`, so:

- `todo` commands on the laptop read the phone's real list and send numbered changes, each applied once
- `web/todo.txt` is a copy of the list on the laptop, refreshed on each `todo` command and `push`. It only seeds a brand-new phone
- if the app is reinstalled or its data is wiped, the list is restored from the mirror. Habits and settings are mirrored the same way, as `habits-state.json` and `settings-state.json`. Back up those files before a factory reset

## The Desk app

A small full-screen app that shows `/sdcard/dash/index.html`. Compared with the phone's browser it:

- hides all bars, keeps the screen on, starts by itself after a reboot, and reopens within about 5 minutes if it crashes
  (not if you left it with Back or Home)
- fetches all data itself over HTTPS, using [Conscrypt](https://github.com/google/conscrypt) and bundled modern root
  certificates. Android 4.4's own TLS can't connect to today's servers. Conscrypt 2.5.3 is the newest release that
  supports Android 4.4, and it is no longer updated, so this is good enough for weather data but not a security boundary
- finds the phone's location from the phone's location providers (GPS, and the network provider, which may be Google's
  or the phone maker's), or from nearby Wi-Fi networks and mobile towers via [beaconDB](https://beacondb.net).
  If none work it uses the place in `web/data.js`

### Privacy

With `place.auto: true`, the app sends nearby Wi-Fi and tower IDs to beaconDB every 15 minutes unless GPS has a recent
fix, your position to Open-Meteo for weather, and to OpenStreetMap Nominatim for the place name.
With `place.auto: false` it does no scanning or position lookups, and uses the place in `web/data.js`.

The page lives on shared storage, where an app with storage permission could replace it. So the page can't reach the
network directly, and the app only fetches from the weather hosts for it.

### Building it

```bash
sudo apt install default-jdk aapt android-sdk-platform-23 dalvik-exchange apksigner zipalign curl zip unzip
android/build.sh                          # downloads Conscrypt once (hash-checked), writes android/build/DeskDash.apk
python3 tools/sync.py app                 # installs the newest build (android/build/ or dist/)
cp android/build/DeskDash.apk dist/       # when you want to commit a new release
```

`build.sh` signs with `android/desk.keystore`, which is **not in the repo** on purpose. Keep a private backup:
Android only accepts an update signed with the same key that signed the installed app. If the key is missing,
`build.sh` makes a new one, and you must uninstall the old app first (`adb uninstall com.deskdash`). The to-do list
comes back from its mirror, as do habits and settings. Cached weather and today's focus sessions are reset.
Set `KS_PASS` to use your own keystore password.

## Credits

Weather and air quality: [Open-Meteo](https://open-meteo.com). Place names: OpenStreetMap Nominatim.
Wi-Fi location: [beaconDB](https://beacondb.net). TLS: [Conscrypt](https://github.com/google/conscrypt) (Apache 2.0).
