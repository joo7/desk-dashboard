// Template for web/data.js, which holds your real location and is not committed. The first push copies this file there.
// EDIT web/data.js on the laptop, then run once: python3 tools/sync.py push
// Everything below runs on the phone by itself; the laptop is only needed to send changes.
var DASH = {
  place: { auto: true, name: "Your City", lat: 0, lon: 0 },
                                 // auto: the Desk app uses the phone's own position; these are used when it has none
  clock24: true,                 // false for AM/PM
  image: "photo.jpg",            // used when no photos were sent with: python3 tools/sync.py photos <folder>
  photoMinutes: 10,              // starting photo interval; after that, change it with the gear icon on the phone
  grayscale: true,               // start photos in black-and-white; change it with the gear icon on the phone
  theme: "photo",                // starting style: "photo" (colours from each photo), "dark", "eink" or "auto" (light, dark at night)
  weekStart: 0,                  // calendar: 0 starts weeks on Sunday, 1 on Monday
  cities: [],   // starting list for the Weather page; after that, add and remove them on the phone
  habits: false,                 // true shows the Habits page again (saved habits are kept)
  events: [],                    // calendar: e.g. { date: "2026-12-25", title: "Holiday" }
  nightFrom: 22, nightTo: 6,     // dark, dimmer page between these hours (remove both to disable)
  todoTitle: "To do",
  weather: true,                 // false hides the weather card
  hourStep: 3,                   // forecast row: one slot every N hours (5 slots)
  monitors: []                   // optional extra tiles, e.g. { label: "Steps", value: "8,200", note: "today" }
};
