# Set up the Desk dashboard on your own old phone

This guide turns an old Android phone into an always-on desk display: a big clock, weather, a photo slideshow, a calendar, countdowns and a focus timer. It takes about 20 minutes.

1. [What you need](#1-what-you-need)
2. [Step by step](#2-step-by-step)
3. [What it can do, with screenshots](#3-what-it-can-do)
4. [Which phones work](#4-which-phones-work)
5. [Wi-Fi and security](#5-wi-fi-and-security)
6. [When something goes wrong](#6-when-something-goes-wrong)

## 1. What you need

**A laptop or desktop (Linux)**

| Needed for | What |
|---|---|
| Everything | Python 3.7 or newer, `adb` (Android Debug Bridge) |
| Photos | ImageMagick (the `convert` command) and any web browser |
| Building the app yourself (optional) | `default-jdk aapt android-sdk-platform-23 dalvik-exchange apksigner zipalign curl zip unzip` |

On Debian or Ubuntu: `sudo apt install adb imagemagick`. The tools use only Python's standard library, so there is nothing to `pip install`. This project was only run on Linux; it may work on macOS or Windows, but nobody has tried.

**The phone**

- Android 4.4 or newer (see [section 4](#4-which-phones-work) for what has been tested)
- A USB cable and a charger. The phone will sit plugged in all the time
- Wi-Fi at home. No SIM card or mobile data is needed
- A few MB of free space for the app, plus about 1.3 MB for each photo
- No Google account, no Play Store sign-in

**Where the laptop and phone must be**

- The same Wi-Fi network, once the first setup is done. During setup the USB cable is enough

## 2. Step by step

### Step 1: Get the code

```bash
git clone <this repository's address>
cd desk-dashboard
```

### Step 2: Prepare the phone

1. Open **Settings > About phone** and tap **Build number** seven times. A message says you are now a developer.
2. Go back to **Settings > Developer options** and switch on **USB debugging**.
3. Join your home Wi-Fi network.
4. Plug the phone into the laptop with the USB cable.
5. A box asks **Allow USB debugging?** Tap **OK**. Tick *Always allow from this computer* only on a laptop you trust.

Check that the laptop can see the phone:

```bash
adb devices
```

You should see one line ending in `device`. If it says `unauthorized`, unlock the phone and accept the box. If the list is empty, try another cable (some cables only charge).

### Step 3: Run the setup

```bash
python3 tools/sync.py setup
```

This does five things and prints each one:

1. Finds the phone and remembers it in `.phone_serial`. From now on the tool only talks to this phone, even if you plug in others.
2. Switches the phone to automatic brightness, keeps the screen on while it is charging, and sets the clock from the network.
3. Reads the phone's Wi-Fi address.
4. Switches `adb` to work over Wi-Fi (port 5555), so you can unplug the cable.
5. Sends the dashboard files to the phone.

Over Wi-Fi, `adb` has no password of its own. Read [section 5](#5-wi-fi-and-security) before you leave it switched on.

### Step 4: Install the Desk app

```bash
python3 tools/sync.py app
```

This installs `dist/DeskDash.apk`, then reopens the dashboard full screen. The app hides the status and navigation bars, keeps the screen on, starts again by itself after a restart, and reopens within about 5 minutes if it ever crashes.

> **Want to be sure what you install?** The file in `dist/` was built by the repository's author. To build your own copy from the source instead, install the build tools from section 1 and run `android/build.sh`. `sync.py app` installs the newest build it finds.

### Step 5: Set your place

The first push created `web/data.js` from a template. Open it and change at least the place:

```js
place: { auto: true, name: "Your City", lat: 51.5074, lon: -0.1278 },
```

- `auto: true` lets the phone find its own position and uses `lat`/`lon` only when it can't. `auto: false` always uses the place you typed and does no location lookups at all (see [section 5](#5-wi-fi-and-security))
- To get `lat` and `lon`, right-click your street on any online map and copy the two numbers
- Other options in the same file: 24-hour or AM/PM clock, which day the week starts on, the hours when the screen goes dark, and your own calendar events

Send the change to the phone:

```bash
python3 tools/sync.py push
```

`web/data.js` holds your location, so it is not committed to git.

### Step 6: Add your photos

```bash
python3 tools/photos_ui.py
```

A page opens in your browser (it runs only on your laptop). Drag pictures onto it, or click **Add photos**. They are resized and sent straight to the phone, and the dashboard shows them within about 10 seconds without restarting. You can also **Hide**, **Show** or **Delete** photos that are already on the phone.

The phone keeps a 1280-pixel copy of each picture, not your original, and the laptop keeps nothing once the page is closed. Keep your originals somewhere safe. To add a whole folder at once instead: `python3 tools/sync.py photos <folder>`.

### Step 7: Make the phone behave as a display

These are optional but worth doing. All of them can be undone in Settings.

| Setting | Why |
|---|---|
| **Location**: on. Choose **High accuracy**, or **Battery saving** if you want the GPS off | The dashboard finds your position and weather from it. If Google asks *Improve location accuracy?*, tap **Agree** |
| **Brightness**: Automatic | Dim in a dark room. The screen is the biggest user of power |
| **Airplane mode** on, then switch **Wi-Fi** back on | Turns off the mobile radio when there is no SIM |
| Leave it plugged in | The screen stays on while charging |

**Look after the battery.** A phone kept at 100% for months ages quickly. This phone cannot stop charging by itself, so the dashboard shows **Unplug charger** in the bottom line at 80% and above, and **Plug in charger** at 30% and below. A cheap timer plug on the charger does it automatically.

### Step 8: Everyday use

| Command | What it does |
|---|---|
| `python3 tools/sync.py push` | Send changes after editing anything in `web/` |
| `python3 tools/photos_ui.py` | Manage the photos |
| `python3 tools/sync.py todo list` | Read the to-do list. Also `add "text"`, `done N`, `rm N` |
| `python3 tools/sync.py doctor` | Test the connection and find what is slow |

On the phone: **swipe sideways** to change page, **drag up or down** to scroll, **tap a photo** for the next one, and tap the **gear** for settings.

**After the phone restarts**, `adb` over Wi-Fi switches itself off. The dashboard comes back on its own, but to send changes you need to plug in USB once and run `python3 tools/sync.py setup` again.

## 3. What it can do

Swipe sideways through seven pages. Every screenshot here shows the real dashboard page at the phone's screen size, with generated sample pictures and a made-up place.

> **How these were made.** They were rendered from the same page in desktop Chrome at 1280 × 720, not photographed from a phone. On a real Android 4.4 phone the fonts and spacing may differ slightly.

### The seven pages

**Home** shows the clock, the date, the weather now and the next five time slots, a photo, air quality, sunrise and sunset, the next holiday, and whether rain is coming. A refresh button on the left of the bottom line updates your position and weather (once a minute at most). Drag up to reach the to-do list.

![Home page with clock, weather and a photo](images/home.jpg)

![To-do list below the home screen](images/home-todo.jpg)

**Photos** is a full-screen slideshow. Tap the left third for the previous photo and the rest for the next.

![Photos page](images/photos.jpg)

**This week** shows today in detail and the next six days.

![This week page](images/week.jpg)

**Weather** shows as many cities as you like. Tap **+ Add city** and search by name.

![Weather page with three cities](images/weather.jpg)

**Countdowns** counts the days left until trips, birthdays and deadlines. Yearly ones repeat.

![Countdowns page](images/countdowns.jpg)

**Calendar** shows the month, your own events and the next holidays. Holidays are the Indian national and festival dates for 2026 and 2027, from `web/holidays.js`.

![Calendar page](images/calendar.jpg)

**Focus** is a timer that beeps when it ends. Use the presets, or drag the slider from 1 minute to 2 hours.

![Focus timer page](images/focus.jpg)

A **Habits** page is also built in. It is off by default; set `habits: true` in `web/data.js` to bring it back.

### The gear menu

Tap the gear (it appears when you touch the screen and fades after a few seconds) to change how often the photo changes (5 seconds to 1 hour), the style, colour or black-and-white photos, when the background goes dark, and the location (automatic, or a place you choose).

![Settings panel](images/settings.jpg)

### Styles

| Photo colours (default) | Pastel |
|---|---|
| ![Photo colours style](images/home.jpg) | ![Pastel style](images/home-pastel.jpg) |
| **Modern dark** | **E-ink** |
| ![Modern dark style](images/home-dark.jpg) | ![E-ink style](images/home-eink.jpg) |

*Photo colours* takes its colours from the current photo, so the whole dashboard changes with each picture. *E-ink* is plain black and white and suits a paper-like screen. A fifth style, *Light, dark at night*, is also available.

### Portrait

Turn the phone and the layout follows. (Your phone's rotation lock is respected.)

![Portrait layout](images/portrait.jpg)

## 4. Which phones work

| Phone | Status |
|---|---|
| **Honor Holly (Hol-U19), Android 4.4.2, 720 × 1280, 1 GB RAM** | **Tested.** This is the phone the project was built and run on |
| Other Android 4.4 phones | Should work. The app is built for Android 4.4 (API 19) as its minimum |
| Android 5 to 9 | The app should install, but this has **not been tested** |
| Android 10 and newer | **Not tested.** These versions limit what an app can do with shared storage and starting itself, so expect problems |
| Android 4.3 and older | **Not supported** |

**Screen size.** The layout scales with the screen, but it has only been checked on a 720p screen. A very small or very large screen is untested.

**Limits to know about**

- The text is English only. Temperatures are in Celsius and wind in km/h, with no setting to change them
- The built-in holidays are Indian ones for 2026 and 2027. For other countries, edit `web/holidays.js`
- Weather and air quality come from [Open-Meteo](https://open-meteo.com), which needs no account. Place names come from OpenStreetMap
- Photos can be JPG, PNG, WebP or GIF. iPhone HEIC files are converted if your ImageMagick can read them, but this has not been tested
- `setup` finds the phone's Wi-Fi address with a command that newer Android versions may not have. If it can't, USB still works

## 5. Wi-Fi and security

Your phone and laptop talk to each other, and the phone talks to the internet, over your Wi-Fi. This section covers what that exposes. It is based on reading the code and on checks made on the tested phone.

### The short version

- **Nothing is listening on the phone by default.** Scanning all 65,535 TCP ports from another computer on the same Wi-Fi found none open
- The risk that matters most is **`adb` over Wi-Fi**, which `setup` switches on. Switch it off when you are done, and never use it on a Wi-Fi network you don't trust
- The phone's operating system **can no longer be patched**. Treat it as a single-purpose device that you don't log into, browse on or install other apps on
- The dashboard sends your **approximate location** to a few public services. Turn that off with `auto: false`

### What I checked

| Check | Result |
|---|---|
| All 65,535 TCP ports of the phone, scanned from the same Wi-Fi | **None open.** UDP was not scanned. At the time, `adb` over Wi-Fi was off because the phone had just restarted |
| Does the app check certificates and server names? | **Yes.** It uses the normal server-name check and trusts the phone's own certificates plus 8 bundled public ones. It does not disable any check |
| Where does the app connect? | Only HTTPS, to `api.open-meteo.com`, `air-quality-api.open-meteo.com`, `geocoding-api.open-meteo.com`, `nominatim.openstreetmap.org` and `api.beacondb.net` |
| Can the dashboard page load anything from the internet? | **No.** The page runs from a local file with network loading blocked, and can only ask the app to fetch from the three Open-Meteo hosts |
| Does the repository contain Wi-Fi passwords or personal addresses? | **No.** The phone's address, its serial number, your location and the signing key are all kept out of git |
| Who can reach the photo page? | Only your laptop. It listens on `127.0.0.1` (confirmed with `ss -ltn`), and refuses requests that come from other websites |

### Risks, from highest to lowest

**1. `adb` over Wi-Fi. Medium to high, while it is switched on.**
`setup` opens port 5555. `adb` gives full control: installing apps and reading or changing files. Its traffic is not encrypted, and anyone on your network can try to connect.

- It normally needs your laptop's key, which the phone accepted at the *Allow USB debugging?* box. Check this is enforced on your phone: `adb shell getprop ro.adb.secure` should print `1`. If it prints `0` or nothing, **anyone on the Wi-Fi can control the phone**, so keep Wi-Fi `adb` off
- Switch it off after setup: with the phone still connected, run `adb usb`. A restart also switches it off
- Use it only on a network you control. On shared Wi-Fi (an office, a hostel, a café) use USB only

**2. An out-of-date phone. Medium, and it can't be fixed.**
Android 4.4 stopped getting security updates years ago, and its built-in web view and system parts have public, unpatched flaws. This is mostly harmless on a locked-down display, because the dashboard never opens web pages from the internet. But the more you use the phone for anything else, the more it matters.

- Don't sign in to any account, open a browser, or install other apps
- Put it on a **guest or IoT network** if your router has one, so a compromised phone can't see your other devices
- Keep Bluetooth and NFC off

**3. Your location leaves the phone. Privacy, low to medium.**
With `auto: true`, every 15 minutes the app may send:

- your position to **Open-Meteo** (weather) and **OpenStreetMap Nominatim** (the place name)
- the **names of nearby Wi-Fi networks and mobile towers** to **beaconDB**, to work out where you are. Networks whose name ends in `_nomap` are left out
- the same kind of nearby-network details to **Google**, if the phone's location mode uses Google's service

These services see your home's rough position and the times you use it. If that matters, set `auto: false` in `web/data.js`: the app then does no scanning or position lookups and uses only the place you typed.

**4. The weather connection itself. Low.**
Everything is HTTPS with certificate checks, so someone on your Wi-Fi can't read or change it. They can see *which* services the phone contacts, and can block it. The security library the app uses to speak modern HTTPS (Conscrypt 2.5.3) is the newest one that works on Android 4.4, and it is no longer updated. That is fine for weather numbers, but it isn't suitable for anything sensitive. Don't extend the app to carry passwords or private data.

**5. Other apps can change the dashboard. Low on a dedicated phone.**
The dashboard files live in shared storage (`/sdcard/dash`), where any app with storage permission could replace them. This matters only if you install other apps.

**6. The app's own doors. Low.**
The app has a receiver that starts it after a restart, which another app on the same phone could trigger. The worst it can do is open the dashboard.

### Do these

- [ ] Use a Wi-Fi network with **WPA2** and a strong password. Android 4.4 can't join WPA3-only networks, and open or WEP networks are unsafe
- [ ] After setup, run `adb usb`, or unplug and rely on USB for later changes
- [ ] Don't forward port 5555 (or any port) on your router
- [ ] Don't sign in to Google or any other account on the phone
- [ ] Prefer a guest network, and turn off Bluetooth and NFC
- [ ] Set `auto: false` if you don't want location lookups
- [ ] If you build the app yourself, set your own signing password: `KS_PASS=your-password android/build.sh`. The default is `deskdash`. Keep `android/desk.keystore` private and backed up
- [ ] If you change `HOST` in `tools/photos_ui.py` away from `127.0.0.1`, anyone on your Wi-Fi could add and delete your photos. Don't

## 6. When something goes wrong

Run `python3 tools/sync.py doctor` first. It checks every step and writes timings to `sync.log`.

| What you see | What to do |
|---|---|
| `adb devices` shows `unauthorized` | Unlock the phone and tap **OK** on the *Allow USB debugging?* box. If it doesn't appear, switch USB debugging off and on |
| `Phone not found` after a restart | Wi-Fi `adb` resets when the phone restarts. Plug in USB and run `python3 tools/sync.py setup` again |
| `adb devices` shows nothing | Try another USB cable or port. Many cables are charge-only |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | An app signed with a different key is installed. Run `adb uninstall com.deskdash`, then `sync.py app` again. Your to-do list and settings come back from their saved copies |
| The screen is blank, or shows `JS error` | Run `python3 tools/sync.py push` again, then `doctor`. The error text is in the bottom line; tap it to read it in full |
| No location, or weather for the wrong place | Check **Settings > Location** is on and accept Google's *Improve location accuracy?* box. If location stops updating after you change a location setting, restart the phone. Or set `auto: false` and type your place |
| The photo page says *Your phone isn't connected* | Plug in USB, or run `setup` again. The page checks again every 10 seconds and updates by itself |
| The footer says **Unplug charger** | The battery is at 80% or more while charging. This is the battery reminder |

To go back to how the phone was: uninstall the app (`adb uninstall com.deskdash`), delete `/sdcard/dash` with `adb shell rm -r /sdcard/dash`, then undo the settings you changed in Settings.
