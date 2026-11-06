package com.deskdash;
import android.content.*;
public class Boot extends BroadcastReceiver {
  @Override public void onReceive(Context c, Intent i) {
    Intent m = new Intent(c, Main.class);
    m.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    c.startActivity(m);
  }
}
