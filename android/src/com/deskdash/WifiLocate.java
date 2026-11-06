package com.deskdash;

import android.content.Context;
import android.location.Location;
import android.net.wifi.*;
import android.telephony.*;
import android.telephony.gsm.GsmCellLocation;
import java.util.List;
import org.json.*;

/** Finds the phone from nearby Wi-Fi networks and mobile towers using beaconDB (open, no Google). */
class WifiLocate {
  static final String URL = "https://api.beacondb.net/v1/geolocate";
  String status = "not tried yet";

  /** Start a Wi-Fi scan; results are read a few seconds later by lookup(). */
  void scan(Context c) {
    try { ((WifiManager) c.getSystemService(Context.WIFI_SERVICE)).startScan(); } catch (Exception e) { }
  }

  /** Blocking network call: run on a background thread. Returns a Location or null (status says why). */
  Location lookup(Context c) {
    android.util.Log.i(Main.TAG, "asking beaconDB");
    try {
      JSONObject req = new JSONObject();
      JSONArray aps = new JSONArray();
      WifiManager wm = (WifiManager) c.getSystemService(Context.WIFI_SERVICE);
      List<ScanResult> rs = wm.getScanResults();
      if (rs != null) for (ScanResult r : rs) {
        if (r.SSID != null && r.SSID.endsWith("_nomap")) continue;  // owner opted out
        JSONObject a = new JSONObject();
        a.put("macAddress", r.BSSID);
        a.put("signalStrength", r.level);
        a.put("frequency", r.frequency);
        aps.put(a);
      }
      JSONArray cells = cells(c);
      if (aps.length() < 2 && cells.length() == 0) {
        status = "Wi-Fi scan found " + aps.length() + " networks (Wi-Fi off?) and no mobile towers";
        return null;
      }
      if (aps.length() >= 2) req.put("wifiAccessPoints", aps);
      if (cells.length() > 0) req.put("cellTowers", cells);
      req.put("considerIp", false);
      req.put("fallbacks", new JSONObject().put("ipf", false).put("lacf", true));
      String r = Net.send(URL, req.toString());
      if (r == null) { status = "beaconDB: no answer or unknown place (" + aps.length() + " Wi-Fi, " + cells.length() + " towers)"; return null; }
      JSONObject j = new JSONObject(r);
      if ("ipf".equals(j.optString("fallback"))) { status = "beaconDB only had an internet-address guess (ignored)"; return null; }
      JSONObject loc = j.getJSONObject("location");
      Location l = new Location(j.has("fallback") ? "towers" : "wifi");
      l.setLatitude(loc.getDouble("lat"));
      l.setLongitude(loc.getDouble("lng"));
      l.setAccuracy((float) j.optDouble("accuracy", 5000));
      l.setTime(System.currentTimeMillis());
      if (l.getAccuracy() > 15000) { status = "beaconDB answer too rough (" + (int) l.getAccuracy() + " m), ignored"; return null; }
      status = "ok from " + l.getProvider() + " (" + aps.length() + " Wi-Fi, " + cells.length() + " towers, \u00B1" + (int) l.getAccuracy() + " m)";
      return l;
    } catch (Exception e) {
      status = "beaconDB error: " + e.getClass().getSimpleName() + " " + e.getMessage();
      return null;
    }
  }

  static JSONArray cells(Context c) {
    JSONArray out = new JSONArray();
    try {
      TelephonyManager tm = (TelephonyManager) c.getSystemService(Context.TELEPHONY_SERVICE);
      List<CellInfo> all = tm.getAllCellInfo();
      if (all != null) for (CellInfo ci : all) {
        if (!ci.isRegistered()) continue;
        JSONObject o = new JSONObject();
        if (ci instanceof CellInfoGsm) {
          CellIdentityGsm id = ((CellInfoGsm) ci).getCellIdentity();
          o.put("radioType", "gsm").put("mobileCountryCode", id.getMcc()).put("mobileNetworkCode", id.getMnc())
           .put("locationAreaCode", id.getLac()).put("cellId", id.getCid());
        } else if (ci instanceof CellInfoWcdma) {
          CellIdentityWcdma id = ((CellInfoWcdma) ci).getCellIdentity();
          o.put("radioType", "wcdma").put("mobileCountryCode", id.getMcc()).put("mobileNetworkCode", id.getMnc())
           .put("locationAreaCode", id.getLac()).put("cellId", id.getCid());
        } else if (ci instanceof CellInfoLte) {
          CellIdentityLte id = ((CellInfoLte) ci).getCellIdentity();
          o.put("radioType", "lte").put("mobileCountryCode", id.getMcc()).put("mobileNetworkCode", id.getMnc())
           .put("locationAreaCode", id.getTac()).put("cellId", id.getCi());
        } else continue;
        if (o.optInt("cellId") > 0 && o.optInt("cellId") != Integer.MAX_VALUE && o.optInt("mobileCountryCode") > 0) out.put(o);
      }
      if (out.length() == 0 && tm.getCellLocation() instanceof GsmCellLocation) {  // older MediaTek phones
        GsmCellLocation g = (GsmCellLocation) tm.getCellLocation();
        String op = tm.getNetworkOperator();
        if (g.getCid() > 0 && op != null && op.length() >= 5) {
          out.put(new JSONObject().put("mobileCountryCode", Integer.parseInt(op.substring(0, 3)))
              .put("mobileNetworkCode", Integer.parseInt(op.substring(3))).put("locationAreaCode", g.getLac())
              .put("cellId", g.getCid()));
        }
      }
    } catch (Exception e) { }
    return out;
  }
}
