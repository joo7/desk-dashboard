# Desk dashboard

Turns an old Android phone (built for an Honor Holly, Android 4.4) into an always-on desk display:
clock, weather with a forecast row, air quality, sunrise/sunset, phone battery, a to-do list you can edit on the phone,
and rotating photos with a full-screen photo view.

Everything runs **on the phone**. The laptop only sends changes over `adb`.

## Layout

```
desk-dashboard/
├── web/            the dashboard, copied to /sdcard/dash on the phone
│   ├── index.html  page (plain ES5 JavaScript so it runs on Android 4.4)
│   ├── data.js     your settings: location, clock, photo timing, night hours, extra tiles
│   ├── todo.txt    starting to-do items (after that the list lives on the phone)
│   └── photo.jpg   default picture
├── tools/
│   └── sync.py     laptop helper: push files, install the app, send photos, diagnostics
├── android/        source of the Desk app (Java; no Gradle or Android Studio needed)
│   ├── AndroidManifest.xml
│   ├── build.sh
│   ├── res/
│   └── src/com/deskdash/
└── dist/
    └── DeskDash.apk   ready-built app
```

Files that are generated or personal (`web/photos/`, `web/tasks.js`, `web/photos.js`, `sync.log`, `.phone_ip`)
and the app signing key are listed in `.gitignore`.

## Quick start

On the phone, turn on USB debugging (Settings > Developer options) and join the same Wi-Fi as the laptop. Then:

```bash
sudo apt install adb imagemagick
python3 tools/sync.py setup                 # first time, phone on USB: settings, Wi-Fi adb, first push
python3 tools/sync.py app                   # install or update the Desk app
```

## Everyday commands

```bash
python3 tools/sync.py push                  # send changes after editing anything in web/
python3 tools/sync.py photos ~/Pictures/x   # send a folder of photos (colour, up to 1280 px)
python3 tools/sync.py todo add "Buy milk"   # or edit the list on the phone itself
python3 tools/sync.py doctor                # check the connection when something is slow
python3 tools/sync.py location on           # switch on the phone's location setting
```

## On the phone

- **Swipe sideways**: switch between the dashboard and the full-screen photo view
- **Tap a photo**: next photo (in the photo view, tap the left side to go back)
- **Colour / B&W** button on the photo: switch the colour mode
- **+ ADD**: add a to-do item. **✕**: delete one. **Tap** an item to tick it

## The Desk app

A small full-screen app that shows `/sdcard/dash/index.html`. Compared with the phone's browser it:

- hides all bars, stays in landscape, keeps the screen on, and starts by itself after a reboot
- fetches data itself, with TLS 1.2 and bundled modern root certificates (old Android lacks both)
- reads battery level and temperature
- finds the phone's location from GPS, or from nearby Wi-Fi networks and mobile towers via
  [beaconDB](https://beacondb.net) (open data, no Google). If neither works it uses the place in `web/data.js`

### Building it

```bash
sudo apt install default-jdk aapt android-sdk-platform-23 dalvik-exchange apksigner zipalign
android/build.sh                          # writes android/build/DeskDash.apk
python3 tools/sync.py app                 # installs the newest build (android/build/ or dist/)
cp android/build/DeskDash.apk dist/       # when you want to commit a new release
```

`build.sh` signs with `android/desk.keystore`, which is **not in the repo** on purpose. Keep a private backup:
Android only accepts an update signed with the same key that signed the installed app. If the key is missing,
`build.sh` makes a new one, and you must uninstall the old app first (`adb uninstall com.deskdash`).
Set `KS_PASS` to use your own keystore password.

## Credits

Weather and air quality: [Open-Meteo](https://open-meteo.com). Place names: OpenStreetMap Nominatim.
Wi-Fi location: [beaconDB](https://beacondb.net).
