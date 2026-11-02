package de.lichtspiel.tv;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Eigener Bildlader: Speicher-Cache (LruCache), Datei-Cache im cacheDir, Laden im Hintergrund. */
public final class Img {
    private static LruCache<String, Bitmap> mem;
    private static File dir;
    private static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    public static void init(Context c) {
        int max = (int) (Runtime.getRuntime().maxMemory() / 6);
        mem = new LruCache<String, Bitmap>(max) {
            @Override protected int sizeOf(String k, Bitmap b) { return b.getByteCount(); }
        };
        dir = new File(c.getCacheDir(), "img");
        dir.mkdirs();
        POOL.execute(Img::trim);
    }

    /** Lädt url in iv; bei Fehler bleibt das Bild leer (Platzhalter liegt darunter). */
    public static void load(ImageView iv, String url) {
        iv.setTag(R_TAG, url);
        if (url == null) { iv.setImageDrawable(null); return; }
        Bitmap b = mem.get(url);
        if (b != null) { iv.setImageBitmap(b); return; }
        iv.setImageDrawable(null);
        POOL.execute(() -> {
            Bitmap bm = fetch(url);
            if (bm != null) mem.put(url, bm);
            MAIN.post(() -> {
                if (url.equals(iv.getTag(R_TAG))) iv.setImageBitmap(bm);
            });
        });
    }

    private static final int R_TAG = R.id.img_url;

    static Bitmap fetch(String url) {
        try {
            File f = new File(dir, hash(url));
            if (!f.exists()) {
                HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(8000);
                c.setReadTimeout(30000);
                c.setRequestProperty("X-Token", App.api.token());
                if (c.getResponseCode() != 200) { c.disconnect(); return null; }
                File tmp = new File(dir, f.getName() + ".tmp");
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(tmp)) {
                    byte[] buf = new byte[16384];
                    int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                }
                c.disconnect();
                if (!tmp.renameTo(f)) return null;
            }
            BitmapFactory.Options o = new BitmapFactory.Options();
            o.inPreferredConfig = Bitmap.Config.RGB_565;
            Bitmap b = BitmapFactory.decodeFile(f.getPath(), o);
            if (b == null) {
                o.inPreferredConfig = Bitmap.Config.ARGB_8888;
                b = BitmapFactory.decodeFile(f.getPath(), o);
            }
            f.setLastModified(System.currentTimeMillis());
            return b;
        } catch (Exception e) {
            return null;
        }
    }

    /** Datei-Cache auf ca. 300 MB begrenzen (älteste zuerst löschen). */
    private static void trim() {
        File[] fs = dir.listFiles();
        if (fs == null) return;
        long total = 0;
        for (File f : fs) total += f.length();
        if (total < 300L * 1024 * 1024) return;
        java.util.Arrays.sort(fs, (a, b) -> Long.compare(a.lastModified(), b.lastModified()));
        for (File f : fs) {
            if (total < 200L * 1024 * 1024) break;
            total -= f.length();
            f.delete();
        }
    }

    static String hash(String s) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-1");
            StringBuilder sb = new StringBuilder();
            for (byte b : md.digest(s.getBytes("UTF-8"))) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            return Integer.toHexString(s.hashCode());
        }
    }
}
