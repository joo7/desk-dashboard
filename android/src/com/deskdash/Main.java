package com.deskdash;

import android.app.Activity;
import android.content.*;
import android.location.*;
import android.os.*;
import android.view.*;
import android.webkit.*;
import java.io.File;
import java.util.List;
import java.util.Locale;
import org.json.JSONObject;

/** Full-screen dashboard: shows /sdcard/dash/index.html and gives the page a few native helpers. */
public class Main extends Activity implements LocationListener {
  static final String PAGE = "/sdcard/dash/index.html";
  WebView web;
  Handler ui = new Handler();
  LocationManager lm;
  Location best;
  String locErr = "";
  WifiLocate wl = new WifiLocate();

  @Override protected void onCreate(Bundle b) {
    super.onCreate(b);
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        | WindowManager.LayoutParams.FLAG_FULLSCREEN
        | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
        | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD);
    Net.init(this);
    web = new WebView(this);
    WebSettings s = web.getSettings();
    s.setJavaScriptEnabled(true);
    s.setDomStorageEnabled(true);
    s.setAllowFileAccess(true);
    s.setAllowFileAccessFromFileURLs(true);
    s.setAllowUniversalAccessFromFileURLs(true);
    s.setCacheMode(WebSettings.LOAD_NO_CACHE);
    web.setBackgroundColor(0xFFECEBE4);
    web.addJavascriptInterface(new Bridge(), "Android");
    web.setWebViewClient(new WebViewClient());
    web.setWebChromeClient(new WebChromeClient());  // lets the page show add/delete dialogs
    setContentView(web);
    startLocation();
    wifiLoop.run();
    load();
  }

  void load() {
    if (new File(PAGE).exists()) {
      web.clearCache(true);
      web.loadUrl("file://" + PAGE);
    } else {
      web.loadData("<body style='font:20px sans-serif;padding:20px'>No dashboard yet.<br>On the laptop run: python3 sync.py push</body>",
          "text/html", "utf-8");
    }
  }

  // ---------- location: ask every provider the phone has; keep the most accurate recent fix
  void startLocation() {
    try {
      lm = (LocationManager) getSystemService(LOCATION_SERVICE);
      for (String p : lm.getProviders(true)) {
        consider(lm.getLastKnownLocation(p));
        if (!LocationManager.PASSIVE_PROVIDER.equals(p)) lm.requestLocationUpdates(p, 15 * 60000L, 200f, this);
      }
    } catch (Exception e) { locErr = e.getClass().getSimpleName() + ": " + e.getMessage(); }
  }

  /** Every 15 minutes: Wi-Fi scan, then ask beaconDB 8 seconds later. */
  Runnable wifiLoop = new Runnable() { public void run() {
    wl.scan(Main.this);
    ui.postDelayed(new Runnable() { public void run() {
      new Thread(new Runnable() { public void run() { consider(wl.lookup(Main.this)); } }).start();
    }}, 8000);
    ui.postDelayed(this, 15 * 60000L);
  }};

  synchronized void consider(Location l) {
    if (l == null) return;
    if (best == null) { best = l; return; }
    long newer = l.getTime() - best.getTime();
    if (newer > 30 * 60000L || (newer > -30 * 60000L && l.getAccuracy() <= best.getAccuracy())) best = l;
  }

  public void onLocationChanged(Location l) { consider(l); }
  public void onStatusChanged(String p, int s, Bundle e) { }
  public void onProviderEnabled(String p) { }
  public void onProviderDisabled(String p) { }

  @Override protected void onDestroy() { ui.removeCallbacks(wifiLoop); try { lm.removeUpdates(this); } catch (Exception e) { } super.onDestroy(); }

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

  /** Methods the page can call as Android.xxx(). */
  class Bridge {
    @JavascriptInterface public String battery() {
      Intent b = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
      JSONObject o = new JSONObject();
      try {
        int lvl = b.getIntExtra("level", -1), sc = b.getIntExtra("scale", 100), st = b.getIntExtra("status", 0);
        o.put("level", sc > 0 ? lvl / (double) sc : 0);
        o.put("charging", st == 2 || st == 5);
        o.put("plugged", b.getIntExtra("plugged", 0) != 0);
        o.put("temp", b.getIntExtra("temperature", 0) / 10.0);
      } catch (Exception e) { }
      return o.toString();
    }

    /** Best position the phone knows, as JSON, or "" if none. Also lists which providers are switched on. */
    @JavascriptInterface public String location() {
      JSONObject o = new JSONObject();
      try {
        o.put("error", locErr);
        o.put("wifi", wl.status);
        if (lm != null) {
          o.put("providers", lm.getProviders(true).toString());
          o.put("all", lm.getAllProviders().toString());
          for (String p : lm.getProviders(true)) consider(lm.getLastKnownLocation(p));
        }
        Location l;
        synchronized (Main.this) { l = best; }
        if (l != null) {
          o.put("lat", l.getLatitude()); o.put("lon", l.getLongitude());
          o.put("acc", l.getAccuracy()); o.put("provider", l.getProvider());
          o.put("age", (System.currentTimeMillis() - l.getTime()) / 60000);
        }
      } catch (Exception e) { try { o.put("error", e.getClass().getSimpleName() + ": " + e.getMessage()); } catch (Exception x) { } }
      return o.toString();
    }

    /** Area name for a position: the phone's geocoder if it has one, else OpenStreetMap. Calls back window[cb](id, name|null). */
    @JavascriptInterface public void name(final double lat, final double lon, final String cb, final int id) {
      new Thread(new Runnable() { public void run() {
        String r = null;
        try {
          if (Geocoder.isPresent()) {
            List<Address> a = new Geocoder(Main.this, Locale.ENGLISH).getFromLocation(lat, lon, 1);
            if (a != null && !a.isEmpty()) {
              Address x = a.get(0);
              String area = x.getSubLocality() != null ? x.getSubLocality() : x.getLocality();
              String city = x.getLocality() != null ? x.getLocality() : x.getAdminArea();
              r = area == null ? city : (city == null || area.equals(city) ? area : area + ", " + city);
            }
          }
        } catch (Exception e) { r = null; }
        if (r == null) {
          try {
            JSONObject a = new JSONObject(Net.get("https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&accept-language=en&lat="
                + lat + "&lon=" + lon)).getJSONObject("address");
            String area = first(a, "suburb", "neighbourhood", "quarter", "village", "town");
            String city = first(a, "city", "town", "county", "state_district", "state");
            r = area == null ? city : (city == null || area.equals(city) ? area : area + ", " + city);
          } catch (Exception e) { r = null; }
        }
        callback(cb, id, r);
      }}).start();
    }

    /** Fetch a URL in the background; the page gets window[cb](id, text) or window[cb](id, null). */
    @JavascriptInterface public void get(final String url, final String cb, final int id) {
      new Thread(new Runnable() { public void run() {
        String r;
        try { r = Net.get(url); } catch (Exception e) { r = null; }
        callback(cb, id, r);
      }}).start();
    }

    @JavascriptInterface public void reload() { ui.post(new Runnable() { public void run() { load(); } }); }
  }

  static String first(JSONObject a, String... keys) {
    for (String k : keys) if (a.optString(k, "").length() > 0) return a.optString(k);
    return null;
  }
}
