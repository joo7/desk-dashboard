package com.deskdash;

import android.content.Context;
import java.io.*;
import java.net.*;
import java.security.KeyStore;
import java.security.cert.*;
import java.util.Collection;
import javax.net.ssl.*;

/** HTTP(S) for Android 4.4: turns on TLS 1.2 and trusts a few modern root certificates the old phone lacks. */
class Net {
  static SSLSocketFactory factory;

  static synchronized void init(Context ctx) {
    if (factory != null) return;
    try {
      TrustManagerFactory sysF = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
      sysF.init((KeyStore) null);
      final X509TrustManager sys = (X509TrustManager) sysF.getTrustManagers()[0];
      KeyStore ks = KeyStore.getInstance(KeyStore.getDefaultType());
      ks.load(null, null);
      InputStream in = ctx.getResources().openRawResource(R.raw.roots);
      Collection<? extends Certificate> cs = CertificateFactory.getInstance("X.509").generateCertificates(in);
      in.close();
      int i = 0;
      for (Certificate c : cs) ks.setCertificateEntry("root" + (i++), c);
      TrustManagerFactory extraF = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
      extraF.init(ks);
      final X509TrustManager extra = (X509TrustManager) extraF.getTrustManagers()[0];
      X509TrustManager both = new X509TrustManager() {
        public void checkClientTrusted(X509Certificate[] ch, String a) throws CertificateException { sys.checkClientTrusted(ch, a); }
        public void checkServerTrusted(X509Certificate[] ch, String a) throws CertificateException {
          try { sys.checkServerTrusted(ch, a); } catch (CertificateException e) { extra.checkServerTrusted(ch, a); }
        }
        public X509Certificate[] getAcceptedIssuers() { return sys.getAcceptedIssuers(); }
      };
      SSLContext ctxTls = SSLContext.getInstance("TLS");
      ctxTls.init(null, new TrustManager[]{both}, null);
      factory = new Tls12(ctxTls.getSocketFactory());
    } catch (Exception e) {
      factory = HttpsURLConnection.getDefaultSSLSocketFactory();
    }
  }

  static String get(String u) throws IOException { return send(u, null); }

  /** POST a JSON body (or GET when body is null); returns the response text or null if not HTTP 200. */
  static String send(String u, String body) throws IOException {
    HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection();
    if (c instanceof HttpsURLConnection && factory != null) ((HttpsURLConnection) c).setSSLSocketFactory(factory);
    c.setConnectTimeout(15000);
    c.setReadTimeout(20000);
    c.setRequestProperty("User-Agent", "DeskDash/1.1 (personal desk dashboard)");
    if (body != null) {
      c.setDoOutput(true);
      c.setRequestMethod("POST");
      c.setRequestProperty("Content-Type", "application/json");
      OutputStream os = c.getOutputStream();
      os.write(body.getBytes("UTF-8"));
      os.close();
    }
    try {
      if (c.getResponseCode() != 200) return null;
      BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
      StringBuilder sb = new StringBuilder();
      char[] buf = new char[4096];
      int n;
      while ((n = in.read(buf)) > 0) sb.append(buf, 0, n);
      in.close();
      return sb.toString();
    } finally { c.disconnect(); }
  }

  /** Same factory, but every socket gets all supported protocols (TLS 1.2 is off by default before Android 5). */
  static class Tls12 extends SSLSocketFactory {
    final SSLSocketFactory f;
    Tls12(SSLSocketFactory f) { this.f = f; }
    Socket on(Socket s) { if (s instanceof SSLSocket) ((SSLSocket) s).setEnabledProtocols(((SSLSocket) s).getSupportedProtocols()); return s; }
    public String[] getDefaultCipherSuites() { return f.getDefaultCipherSuites(); }
    public String[] getSupportedCipherSuites() { return f.getSupportedCipherSuites(); }
    public Socket createSocket(Socket s, String h, int p, boolean a) throws IOException { return on(f.createSocket(s, h, p, a)); }
    public Socket createSocket(String h, int p) throws IOException { return on(f.createSocket(h, p)); }
    public Socket createSocket(String h, int p, InetAddress l, int lp) throws IOException { return on(f.createSocket(h, p, l, lp)); }
    public Socket createSocket(InetAddress h, int p) throws IOException { return on(f.createSocket(h, p)); }
    public Socket createSocket(InetAddress h, int p, InetAddress l, int lp) throws IOException { return on(f.createSocket(h, p, l, lp)); }
  }
}
