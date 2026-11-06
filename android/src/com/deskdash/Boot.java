package com.deskdash;
import android.content.*;
/** Opens the dashboard after a reboot, and reopens it (via the watchdog alarm) if its process has died. */
public class Boot extends BroadcastReceiver {
  static final String WATCH = "com.deskdash.WATCH", WANTED = "wanted";

  static SharedPreferences prefs(Context c) { return c.getSharedPreferences("desk", Context.MODE_PRIVATE); }

  @Override public void onReceive(Context c, Intent i) {
    if (WATCH.equals(i.getAction()) && (Main.alive || !prefs(c).getBoolean(WANTED, false))) return;
    Intent m = new Intent(c, Main.class);
    m.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    c.startActivity(m);
  }
}
