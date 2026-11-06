package com.deskdash;

import android.app.Activity;
import android.app.AlarmManager;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.app.PendingIntent;
import android.content.*;
import android.location.*;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.*;
import android.util.Log;
import android.view.*;
import android.webkit.*;
import android.widget.DatePicker;
import android.widget.EditText;
import java.io.*;
import java.net.URL;
import java.util.Calendar;
import java.util.Locale;
import org.json.JSONObject;

/** Full-screen dashboard: shows /sdcard/dash/index.html and gives the page a few native helpers. */
public class Main extends Activity implements LocationListener {
  static final String PAGE = "/sdcard/dash/index.html";
  static final String DIR = "/sdcard/dash/";
  static final long WATCH_EVERY = 5 * 60000L;
  static final String TAG = "DeskDash";
  /** True while this process has the dashboard open; a restarted process starts false. Read by the watchdog. */
  static volatile boolean alive;

  WebView web;
  Handler ui = new Handler();
  LocationManager lm;
  Location best;
  boolean locating;
  String locErr = "";
  WifiLocate wl = new WifiLocate();

  @Override protected void onCreate(Bundle b) {
    super.onCreate(b);
    alive = true;
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        | WindowManager.LayoutParams.FLAG_FULLSCREEN
        | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
        | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD);
    Net.init(this);
    lm = (LocationManager) getSystemService(LOCATION_SERVICE);
    web = new WebView(this);
    WebSettings s = web.getSettings();
    s.setJavaScriptEnabled(true);
    s.setDomStorageEnabled(true);
    // The page lives on shared storage, so it gets as little as possible: local files only, no direct
    // network. All its data comes through Bridge.get, which only reaches the weather hosts.
    // FileAccessFromFileURLs must stay on: without it a file:// page gets no localStorage on Android 4.4.
    s.setAllowFileAccess(true);
    s.setAllowFileAccessFromFileURLs(true);
    s.setAllowUniversalAccessFromFileURLs(false);
    s.setBlockNetworkLoads(true);
    s.setCacheMode(WebSettings.LOAD_NO_CACHE);
    web.setBackgroundColor(0xFF0E0F11);
    web.addJavascriptInterface(new Bridge(), "Android");
    web.setWebViewClient(new WebViewClient() {
      @Override public boolean shouldOverrideUrlLoading(WebView v, String url) { return true; }  // never navigate away
    });
    web.setWebChromeClient(new WebChromeClient() {  // lets the page show add/delete dialogs
      @Override public boolean onJsAlert(WebView v, String u, String msg, JsResult r) { return dialog(msg, null, r, null); }
      @Override public boolean onJsConfirm(WebView v, String u, String msg, JsResult r) { return dialog(msg, null, r, null); }
      @Override public boolean onJsPrompt(WebView v, String u, String msg, String val, JsPromptResult r) { return dialog(msg, val == null ? "" : val, r, r); }
      @Override public boolean onConsoleMessage(ConsoleMessage m) {
        Log.i(TAG, "page: " + m.message() + " (line " + m.lineNumber() + ")");
        return true;
      }
    });
    setContentView(web);
    startWatchdog();
    load();
  }

  /** Plain dialogs for the page; the WebView's own carry an odd title on file:// pages. input != null makes it a prompt. */
  boolean dialog(String msg, String input, final JsResult r, final JsPromptResult pr) {
    final EditText edit = input == null ? null : new EditText(this);
    AlertDialog.Builder d = new AlertDialog.Builder(this, AlertDialog.THEME_HOLO_LIGHT).setMessage(msg)
        .setPositiveButton(android.R.string.ok, new DialogInterface.OnClickListener() { public void onClick(DialogInterface x, int w) {
          if (pr != null) pr.confirm(edit.getText().toString()); else r.confirm();
        }})
        .setOnCancelListener(new DialogInterface.OnCancelListener() { public void onCancel(DialogInterface x) { r.cancel(); }})
        .setNegativeButton(android.R.string.cancel, new DialogInterface.OnClickListener() { public void onClick(DialogInterface x, int w) { r.cancel(); }});
    if (edit != null) { edit.setSingleLine(true); edit.setText(input); d.setView(edit); }
    AlertDialog shown = d.create();
    if (edit != null) shown.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE);
    shown.show();
    return true;
  }

  void load() {
    if (new File(PAGE).exists()) {
      web.clearCache(true);
      web.loadUrl("file://" + PAGE);
    } else {
      web.loadData("<body style='font:20px sans-serif;padding:20px'>No dashboard yet.<br>On the laptop run: python3 tools/sync.py push</body>",
          "text/html", "utf-8");
    }
  }

  // ---------- watchdog: reopens the dashboard if the process dies, but not if you chose to leave it
  void startWatchdog() {
    Intent i = new Intent(this, Boot.class).setAction(Boot.WATCH);
    PendingIntent pi = PendingIntent.getBroadcast(this, 0, i, PendingIntent.FLAG_UPDATE_CURRENT);
    ((AlarmManager) getSystemService(ALARM_SERVICE)).setInexactRepeating(AlarmManager.ELAPSED_REALTIME,
        SystemClock.elapsedRealtime() + WATCH_EVERY, WATCH_EVERY, pi);
  }

  void setWanted(boolean w) { Boot.prefs(this).edit().putBoolean(Boot.WANTED, w).apply(); }

  @Override protected void onResume() { super.onResume(); setWanted(true); }
  @Override public void onBackPressed() { setWanted(false); super.onBackPressed(); }
  @Override protected void onUserLeaveHint() { setWanted(false); super.onUserLeaveHint(); }

  // ---------- location: only runs when the page asks for it (place.auto in data.js)
  /** Ask every provider the phone has and start the Wi-Fi lookups, or stop all of that. */
  synchronized void setLocating(boolean on) {
    if (on == locating) return;
    locating = on;
    Log.i(TAG, "location lookups " + (on ? "on" : "off"));
    if (on) {
      startProviders();
      ui.post(wifiLoop);
    } else {
      ui.removeCallbacks(wifiLoop);
      ui.removeCallbacks(wifiLookup);
      try { lm.removeUpdates(this); lm.removeUpdates(once); } catch (Exception e) { }
      best = null;
    }
  }

  /** Listens to every provider, not just the enabled ones, so switching location on later is picked up. */
  void startProviders() {
    try { lm.removeUpdates(this); lm.removeUpdates(once); } catch (Exception e) { }
    locErr = "";
    for (String p : lm.getAllProviders()) {
      if (LocationManager.PASSIVE_PROVIDER.equals(p)) continue;
      try { lm.requestLocationUpdates(p, 15 * 60000L, 200f, this, ui.getLooper()); }
      catch (Exception e) { locErr = e.getClass().getSimpleName() + ": " + e.getMessage(); }
    }
    try { for (String p : lm.getProviders(true)) consider(lm.getLastKnownLocation(p)); }
    catch (Exception e) { locErr = e.getClass().getSimpleName() + ": " + e.getMessage(); }
    askOnce();
  }

  /** Slow repeating updates can stay silent for a long time, so also ask for one position right now. */
  void askOnce() {
    for (String p : lm.getAllProviders()) {
      if (LocationManager.PASSIVE_PROVIDER.equals(p)) continue;
      try { lm.requestSingleUpdate(p, once, ui.getLooper()); Log.i(TAG, "asked " + p + " for a position"); }
      catch (Exception e) { Log.i(TAG, p + " refused: " + e.getMessage()); }
    }
  }

  /** Separate from the repeating listener: a one-shot request on the same listener would replace it. */
  final LocationListener once = new LocationListener() {
    public void onLocationChanged(Location l) { consider(l); }
    public void onStatusChanged(String p, int s, Bundle e) { Log.i(TAG, p + " status " + s); }
    public void onProviderEnabled(String p) { Log.i(TAG, p + " switched on"); }
    public void onProviderDisabled(String p) { Log.i(TAG, p + " switched off"); }
  };

  /** Every 15 minutes: Wi-Fi scan, then ask beaconDB 8 seconds later. Skipped while GPS has a recent fix. */
  Runnable wifiLoop = new Runnable() { public void run() {
    if (gpsIsCurrent()) wl.status = "not needed, GPS is current";
    else { askOnce(); wl.scan(Main.this); ui.postDelayed(wifiLookup, 8000); }
    ui.postDelayed(this, 15 * 60000L);
  }};

  Runnable wifiLookup = new Runnable() { public void run() {
    new Thread(new Runnable() { public void run() { consider(wl.lookup(Main.this)); Log.i(TAG, "Wi-Fi lookup: " + wl.status); } }).start();
  }};

  synchronized boolean gpsIsCurrent() {
    return best != null && LocationManager.GPS_PROVIDER.equals(best.getProvider())
        && System.currentTimeMillis() - best.getTime() < 30 * 60000L;
  }

  synchronized void consider(Location l) {
    if (l == null || !locating) return;
    Log.i(TAG, "location from " + l.getProvider() + ", accuracy " + (int) l.getAccuracy() + " m, age " + (System.currentTimeMillis() - l.getTime()) / 60000 + " min");
    if (best == null) { best = l; return; }
    long newer = l.getTime() - best.getTime();
    if (newer > 30 * 60000L || (newer > -30 * 60000L && l.getAccuracy() <= best.getAccuracy())) best = l;
  }

  public void onLocationChanged(Location l) { consider(l); }
  public void onStatusChanged(String p, int s, Bundle e) { }
  public void onProviderEnabled(String p) { }
  public void onProviderDisabled(String p) { }

  @Override protected void onDestroy() { alive = false; setLocating(false); super.onDestroy(); }

  @Override protected void onNewIntent(Intent i) { super.onNewIntent(i); load(); }

  @Override public void onWindowFocusChanged(boolean f) {
    super.onWindowFocusChanged(f);
    if (f) web.setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN
        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
  }

  void callback(final String cb, final int id, final String r) {
    final String js = cb + "(" + id + "," + (r == null ? "null" : JSONObject.quote(r)) + ")";
    ui.post(new Runnable() { public void run() { web.evaluateJavascript(js, null); } });
  }

  /** Where saved data named by the page goes; only plain names, so the page can't write elsewhere. */
  static File stateFile(String name) {
    return name != null && name.matches("[a-z]+") ? new File(DIR + name + "-state.json") : null;
  }

  /** The only hosts the page may fetch from. */
  static boolean allowed(String u) {
    try {
      URL x = new URL(u);
      return "https".equals(x.getProtocol())
          && ("api.open-meteo.com".equals(x.getHost()) || "air-quality-api.open-meteo.com".equals(x.getHost())
              || "geocoding-api.open-meteo.com".equals(x.getHost()));
    } catch (Exception e) { return false; }
  }

  /** Methods the page can call as Android.xxx(). */
  class Bridge {
    @JavascriptInterface public void locate(boolean on) { setLocating(on); }

    /** Ask for a position now: listens again, scans Wi-Fi, looks it up, then calls back window[cb](id, status). */
    @JavascriptInterface public void refreshLocation(final String cb, final int id) {
      ui.post(new Runnable() { public void run() {
        if (!locating) { callback(cb, id, null); return; }
        startProviders();
        wl.scan(Main.this);
        ui.postDelayed(new Runnable() { public void run() {
          new Thread(new Runnable() { public void run() {
            consider(wl.lookup(Main.this));
            Log.i(TAG, "Wi-Fi lookup: " + wl.status);
            callback(cb, id, wl.status);
          }}).start();
        }}, 8000);
      }});
    }

    /** Best position the phone knows, as JSON. Also lists which providers are switched on. */
    @JavascriptInterface public String location() {
      JSONObject o = new JSONObject();
      try {
        o.put("error", locErr);
        o.put("wifi", wl.status);
        if (locating) {
          // String.valueOf, not list.toString(): built against a newer SDK, that call does not resolve on Android 4.4
          o.put("providers", String.valueOf((Object) lm.getProviders(true)));
          o.put("all", String.valueOf((Object) lm.getAllProviders()));
          for (String p : lm.getProviders(true)) consider(lm.getLastKnownLocation(p));
        }
        Location l;
        synchronized (Main.this) { l = best; }
        if (l != null) {
          o.put("lat", l.getLatitude()); o.put("lon", l.getLongitude());
          o.put("acc", l.getAccuracy()); o.put("provider", l.getProvider());
          o.put("age", (System.currentTimeMillis() - l.getTime()) / 60000);
        }
      } catch (Throwable e) {
        Log.w(TAG, "location failed", e);
        try { o.put("error", e.getClass().getSimpleName() + ": " + e.getMessage()); } catch (Exception x) { }
      }
      return o.toString();
    }

    /** Area name for a position, from OpenStreetMap. Calls back window[cb](id, name|null). */
    @JavascriptInterface public void name(final double lat, final double lon, final String cb, final int id) {
      new Thread(new Runnable() { public void run() {
        String r = null;
        try {
          JSONObject a = new JSONObject(Net.get("https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&accept-language=en&lat="
              + lat + "&lon=" + lon)).getJSONObject("address");
          String area = first(a, "suburb", "neighbourhood", "quarter", "village", "town");
          String city = first(a, "city", "town", "county", "state_district", "state");
          r = area == null ? city : (city == null || area.equals(city) ? area : area + ", " + city);
        } catch (Exception e) { r = null; }
        callback(cb, id, r);
      }}).start();
    }

    /** Fetch a weather URL in the background; the page gets window[cb](id, text) or window[cb](id, null). */
    @JavascriptInterface public void get(final String url, final String cb, final int id) {
      new Thread(new Runnable() { public void run() {
        String r = null;
        if (allowed(url)) try { r = Net.get(url); } catch (Exception e) { Log.w(TAG, "fetch failed: " + url, e); }
        else Log.w(TAG, "fetch refused: " + url);
        callback(cb, id, r);
      }}).start();
    }

    /** Mirror saved data to shared storage: the laptop can read it, and a reinstall can restore from it.
     *  Returns "" or the error text (an exception must not cross the JavaScript bridge). */
    @JavascriptInterface public String saveState(String name, String json) {
      File f = stateFile(name);
      if (f == null) return "bad name";
      try {
        File tmp = new File(f.getPath() + ".tmp");
        Writer w = new OutputStreamWriter(new FileOutputStream(tmp), "UTF-8");
        try { w.write(json); } finally { w.close(); }
        if (!tmp.renameTo(f)) return "could not save " + f;
        return "";
      } catch (IOException e) { return e.getMessage(); }
    }

    /** The mirrored data, or "" if there is none. */
    @JavascriptInterface public String loadState(String name) {
      File f = stateFile(name);
      if (f == null) return "";
      StringBuilder sb = new StringBuilder();
      try {
        Reader r = new InputStreamReader(new FileInputStream(f), "UTF-8");
        try {
          char[] buf = new char[4096];
          int n;
          while ((n = r.read(buf)) > 0) sb.append(buf, 0, n);
        } finally { r.close(); }
      } catch (IOException e) { return ""; }
      return sb.toString();
    }

    /** Native date picker. Calls back window[cb](id, "yyyy-mm-dd"), or (id, null) if cancelled. */
    @JavascriptInterface public void pickDate(final String cb, final int id) {
      ui.post(new Runnable() { public void run() {
        Calendar c = Calendar.getInstance();
        // No listener passed in: on Android 4.4 it also fires on Cancel.
        final DatePickerDialog d = new DatePickerDialog(Main.this, AlertDialog.THEME_HOLO_LIGHT, null,
            c.get(Calendar.YEAR), c.get(Calendar.MONTH), c.get(Calendar.DAY_OF_MONTH));
        d.setButton(DialogInterface.BUTTON_POSITIVE, getString(android.R.string.ok), new DialogInterface.OnClickListener() {
          public void onClick(DialogInterface x, int w) {
            DatePicker p = d.getDatePicker();
            callback(cb, id, String.format(Locale.US, "%04d-%02d-%02d", p.getYear(), p.getMonth() + 1, p.getDayOfMonth()));
          }});
        d.setButton(DialogInterface.BUTTON_NEGATIVE, getString(android.R.string.cancel), new DialogInterface.OnClickListener() {
          public void onClick(DialogInterface x, int w) { callback(cb, id, null); }});
        d.setOnCancelListener(new DialogInterface.OnCancelListener() { public void onCancel(DialogInterface x) { callback(cb, id, null); }});
        d.show();
      }});
    }

    /** Timer finished. */
    @JavascriptInterface public void beep() {
      try {
        final ToneGenerator t = new ToneGenerator(AudioManager.STREAM_ALARM, 100);
        t.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 1500);
        ui.postDelayed(new Runnable() { public void run() { t.release(); } }, 2000);
      } catch (RuntimeException e) { Log.w(TAG, "beep failed", e); }
    }

    @JavascriptInterface public void reload() { ui.post(new Runnable() { public void run() { load(); } }); }
  }

  static String first(JSONObject a, String... keys) {
    for (String k : keys) if (a.optString(k, "").length() > 0) return a.optString(k);
    return null;
  }
}
