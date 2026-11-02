package de.lichtspiel.tv;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Zugriff auf die Lichtspiel-Server-API (HttpURLConnection + org.json aus dem Android-SDK). */
public final class Api {
    public interface Cb { void done(Object result, String error); }

    public static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private final SharedPreferences sp;
    public JSONObject prefs = new JSONObject();
    public JSONObject user;

    public Api(Context c) {
        sp = c.getSharedPreferences("lichtspiel", Context.MODE_PRIVATE);
    }

    public String server() {
        String s = sp.getString("server", "");
        return s.endsWith("/") ? s.substring(0, s.length() - 1) : s;
    }
    public void setServer(String s) { sp.edit().putString("server", s.trim()).apply(); }
    public String token() { return sp.getString("token", ""); }
    public void setToken(String t) { sp.edit().putString("token", t == null ? "" : t).apply(); }
    public SharedPreferences local() { return sp; }

    public String url(String path) { return server() + path; }

    public Map<String, String> headers() {
        Map<String, String> h = new HashMap<>();
        h.put("X-Token", token());
        h.put("X-Client", "tv");
        return h;
    }

    /** Synchroner Aufruf – nur in Hintergrund-Threads verwenden. */
    public Object call(String method, String path, Object body) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url(path)).openConnection();
        c.setConnectTimeout(8000);
        c.setReadTimeout(60000);
        c.setRequestMethod(method);
        c.setRequestProperty("X-Token", token());
        c.setRequestProperty("X-Client", "tv");
        if (body != null) {
            byte[] b = body.toString().getBytes(StandardCharsets.UTF_8);
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            c.setFixedLengthStreamingMode(b.length);
            try (OutputStream o = c.getOutputStream()) { o.write(b); }
        }
        int code = c.getResponseCode();
        InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
        String txt = in == null ? "" : read(in);
        c.disconnect();
        Object j = txt.isEmpty() ? new JSONObject() : new JSONTokener(txt).nextValue();
        if (code >= 400) {
            String msg = (j instanceof JSONObject) ? ((JSONObject) j).optString("error", "Fehler " + code) : "Fehler " + code;
            if (code == 401) msg = "401:" + msg;
            throw new Exception(msg);
        }
        return j;
    }

    public static String read(InputStream in) throws Exception {
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
        in.close();
        return bo.toString("UTF-8");
    }

    public void async(String method, String path, Object body, Cb cb) {
        POOL.execute(() -> {
            Object r = null;
            String err = null;
            try { r = call(method, path, body); } catch (Exception e) { err = e.getMessage() == null ? e.toString() : e.getMessage(); }
            final Object fr = r; final String fe = err;
            if (cb != null) MAIN.post(() -> cb.done(fr, fe));
        });
    }
    public void get(String path, Cb cb) { async("GET", path, null, cb); }
    public void post(String path, Object body, Cb cb) { async("POST", path, body == null ? new JSONObject() : body, cb); }
    public void put(String path, Object body, Cb cb) { async("PUT", path, body, cb); }

    public static JSONObject obj(Object... kv) {
        JSONObject o = new JSONObject();
        try { for (int i = 0; i + 1 < kv.length; i += 2) o.put((String) kv[i], kv[i + 1]); } catch (Exception ignored) { }
        return o;
    }
    public static JSONArray arr(Object o) { return o instanceof JSONArray ? (JSONArray) o : new JSONArray(); }
    public static JSONObject o(Object o) { return o instanceof JSONObject ? (JSONObject) o : new JSONObject(); }

    public int prefInt(String k, int d) { return prefs.optInt(k, d); }
    public boolean prefBool(String k, boolean d) { return prefs.optBoolean(k, d); }
    public String prefStr(String k, String d) { return prefs.optString(k, d); }
}
