package de.lichtspiel.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.drawable.GradientDrawable;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** Wiedergabe mit dem MediaPlayer des Android-SDK. */
public class PlayerActivity extends Activity implements SurfaceHolder.Callback {
    public static void play(Activity a, int id, double start) {
        a.startActivity(new Intent(a, PlayerActivity.class).putExtra("id", id).putExtra("start", start));
    }

    public static void tune(Activity a, int cid, String name) {
        a.startActivity(new Intent(a, PlayerActivity.class).putExtra("tv", cid).putExtra("tv_name", name));
    }

    private final Handler h = new Handler(Looper.getMainLooper());
    private MediaPlayer mp;
    private SurfaceView surface;
    private SurfaceHolder holder;
    private FrameLayout root, overlay;
    private TextView tTitle, tSub, tInfo, tTime, tEnd, tCue, actionBtn;
    private SeekView seek;
    private ProgressBar spin;
    private JSONObject info;
    private int itemId, tvId, liveId, fallback, vw, vh;
    private String tvName;
    private int[] liveIds;
    private String[] liveNames;
    private double offset, pendingSeek = -1, lastRep;
    private Integer height;
    private boolean prepared, closing, nuDismissed;
    private long nuAt;
    private final List<double[]> cueT = new ArrayList<>();
    private final List<String> cueX = new ArrayList<>();
    private String liveMode = "copy";
    private static JSONObject caps;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        build();
        Intent it = getIntent();
        tvId = it.getIntExtra("tv", 0);
        tvName = it.getStringExtra("tv_name");
        liveId = it.getIntExtra("live", 0);
        liveIds = it.getIntArrayExtra("live_ids");
        liveNames = it.getStringArrayExtra("live_names");
    }

    private boolean started;

    @Override public void surfaceCreated(SurfaceHolder sh) {
        if (mp != null) mp.setDisplay(sh);
        if (started) return;
        started = true;
        if (liveId > 0) startLive(liveId);
        else if (tvId > 0) tuneNow();
        else start(getIntent().getIntExtra("id", 0), getIntent().getDoubleExtra("start", 0), null, null, null, null);
    }
    @Override public void surfaceChanged(SurfaceHolder sh, int f, int w, int hh) { }
    @Override public void surfaceDestroyed(SurfaceHolder sh) { if (mp != null) mp.setDisplay(null); }

    // ------------------------------------------------------------ Aufbau
    private void build() {
        root = new FrameLayout(this);
        root.setBackgroundColor(0xff000000);
        surface = new SurfaceView(this);
        holder = surface.getHolder();
        holder.addCallback(this);
        root.addView(surface, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH, Gravity.CENTER));
        tCue = Ui.text(this, "", 30 * subScale(), 0xffffffff, true);
        tCue.setGravity(Gravity.CENTER);
        tCue.setShadowLayer(6, 2, 2, 0xff000000);
        FrameLayout.LayoutParams cp = new FrameLayout.LayoutParams(Ui.MATCH, Ui.WRAP, Gravity.BOTTOM);
        cp.setMargins(Ui.dp(this, 80), 0, Ui.dp(this, 80), Ui.dp(this, 50));
        root.addView(tCue, cp);
        spin = new ProgressBar(this);
        root.addView(spin, new FrameLayout.LayoutParams(Ui.dp(this, 64), Ui.dp(this, 64), Gravity.CENTER));

        overlay = new FrameLayout(this);
        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.VERTICAL);
        top.setPadding(Ui.dp(this, 48), Ui.dp(this, 30), Ui.dp(this, 48), Ui.dp(this, 70));
        top.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0xdd000000, 0x00000000}));
        tTitle = Ui.text(this, "", 26, 0xffffffff, true);
        tSub = Ui.text(this, "", 18, 0xffcbd5e1, false);
        tInfo = Ui.text(this, "", 14, 0xff94a3b8, false);
        top.addView(tTitle);
        top.addView(tSub);
        top.addView(tInfo, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 4, 0, 0));
        overlay.addView(top, new FrameLayout.LayoutParams(Ui.MATCH, Ui.WRAP, Gravity.TOP));
        LinearLayout bot = new LinearLayout(this);
        bot.setOrientation(LinearLayout.VERTICAL);
        bot.setPadding(Ui.dp(this, 48), Ui.dp(this, 70), Ui.dp(this, 48), Ui.dp(this, 28));
        bot.setBackground(new GradientDrawable(GradientDrawable.Orientation.BOTTOM_TOP, new int[]{0xee000000, 0x00000000}));
        seek = new SeekView(this);
        bot.addView(seek, Ui.lp(Ui.MATCH, Ui.dp(this, 22)));
        LinearLayout tr = new LinearLayout(this);
        tTime = Ui.text(this, "", 17, 0xffe2e8f0, false);
        tEnd = Ui.text(this, "", 15, 0xff94a3b8, false);
        tr.addView(tTime, new LinearLayout.LayoutParams(0, Ui.WRAP, 1));
        tr.addView(tEnd);
        bot.addView(tr, Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 0, 6, 0, 0));
        TextView hint = Ui.text(this, "OK Pause · ←/→ Spulen · ↑ Ton, Untertitel, Qualität · Zurück Beenden", 13, 0xff64748b, false);
        bot.addView(hint, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 6, 0, 0));
        overlay.addView(bot, new FrameLayout.LayoutParams(Ui.MATCH, Ui.WRAP, Gravity.BOTTOM));
        root.addView(overlay, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));

        actionBtn = Ui.button(this, "", null);
        actionBtn.setVisibility(View.GONE);
        FrameLayout.LayoutParams ap = new FrameLayout.LayoutParams(Ui.WRAP, Ui.WRAP, Gravity.BOTTOM | Gravity.END);
        ap.setMargins(0, 0, Ui.dp(this, 48), Ui.dp(this, 150));
        root.addView(actionBtn, ap);
        setContentView(root);
        h.post(tick);
    }

    private float subScale() { return App.api.prefInt("sub_size", 100) / 100f; }

    // ------------------------------------------------------------ Fähigkeiten des Geräts
    static JSONObject caps() {
        if (caps != null) return caps;
        JSONArray vc = new JSONArray(), ac = new JSONArray(), ct = new JSONArray();
        String[][] v = {{"video/avc", "h264"}, {"video/hevc", "hevc"}, {"video/x-vnd.on2.vp9", "vp9"}, {"video/av01", "av1"}, {"video/mpeg2", "mpeg2video"}};
        String[][] a = {{"audio/mp4a-latm", "aac"}, {"audio/mpeg", "mp3"}, {"audio/ac3", "ac3"}, {"audio/eac3", "eac3"},
                {"audio/flac", "flac"}, {"audio/opus", "opus"}, {"audio/vorbis", "vorbis"}};
        MediaCodecInfo[] all = new MediaCodecList(MediaCodecList.REGULAR_CODECS).getCodecInfos();
        for (String[][] list : new String[][][]{v, a}) {
            for (String[] t : list) {
                boolean ok = false;
                for (MediaCodecInfo ci : all) {
                    if (ci.isEncoder()) continue;
                    for (String type : ci.getSupportedTypes()) if (type.equalsIgnoreCase(t[0])) { ok = true; break; }
                    if (ok) break;
                }
                if (ok) (list == v ? vc : ac).put(t[1]);
            }
        }
        ct.put("mp4"); ct.put("mkv"); ct.put("webm");
        caps = Api.obj("vc", vc, "ac", ac, "ct", ct, "tracks", true);
        return caps;
    }

    // ------------------------------------------------------------ Start
    private void start(int id, double t, Integer audio, String sub, Integer hgt, String force) {
        itemId = id;
        height = hgt;
        nuDismissed = false;
        actionBtn.setVisibility(View.GONE);
        spin.setVisibility(View.VISIBLE);
        JSONObject body = Api.obj("caps", caps(), "start", t, "height", hgt == null ? 0 : hgt);
        try {
            if (audio != null) body.put("audio", audio);
            if (sub != null) body.put("sub", sub);
            if (force != null) body.put("force", force);
            if (tvId > 0) body.put("start", t);
        } catch (Exception ignored) { }
        App.api.post("/api/play/" + id, body, (r, e) -> {
            if (closing) return;
            if (e != null) { fail(e); return; }
            info = Api.o(r);
            boolean ep = "episode".equals(info.optString("kind"));
            tTitle.setText(ep ? info.optString("show_title") : info.optString("title"));
            String s = ep ? "Staffel " + info.optInt("season") + " · Folge " + info.optInt("episode") + " – " + info.optString("title")
                    : (info.optInt("year") > 0 ? String.valueOf(info.optInt("year")) : "");
            if (tvId > 0) s = "📺 " + tvName + (s.isEmpty() ? "" : " · " + s);
            tSub.setText(s);
            infoLine();
            loadSubs(info.isNull("sub_sel") ? null : info.optString("sub_sel"));
            setSource(info.optDouble("start", 0));
            showOverlay();
        });
    }

    private void infoLine() {
        String mode = info.optString("mode").replace("*", "");
        mode = mode.equals("direct") ? "Direkt" : mode.equals("remux") ? "Remux" : "Umgewandelt";
        JSONObject v = info.optJSONObject("video");
        String a = "";
        JSONArray au = info.optJSONArray("audio");
        for (int i = 0; au != null && i < au.length(); i++) {
            JSONObject x = au.optJSONObject(i);
            if (x.optInt("i") == info.optInt("audio_sel", -1)) a = Ui.lang(x.optString("lang")) + " " + Ui.codec(x.optString("codec")) + " " + Ui.channels(x.optInt("channels"));
        }
        String vs = v != null ? Ui.codec(v.optString("codec")) + " " + v.optInt("height") + "p" : "";
        long br = info.optLong("bitrate") / 1000;
        tInfo.setText(mode + " · " + vs + (a.isEmpty() ? "" : " · " + a) + (br > 0 ? " · " + br + " kbit/s" : "") +
                (height != null && height > 0 ? " · → " + height + "p" : ""));
    }

    private void setSource(double t) {
        prepared = false;
        spin.setVisibility(View.VISIBLE);
        release();
        boolean direct = "direct".equals(info.optString("mode"));
        offset = direct ? 0 : t;
        String url = App.api.url(info.optString("url")) + (direct ? "" : "&t=" + String.format(Locale.ROOT, "%.2f", t));
        mp = new MediaPlayer();
        try {
            mp.setDataSource(this, Uri.parse(url), App.api.headers());
        } catch (Exception e) { fail(e.toString()); return; }
        mp.setDisplay(holder);
        mp.setScreenOnWhilePlaying(true);
        mp.setOnVideoSizeChangedListener((m, w, hh) -> { vw = w; vh = hh; layoutVideo(); });
        mp.setOnPreparedListener(m -> {
            prepared = true;
            if (direct) {
                selectAudio(m);
                if (t > 0) m.seekTo((long) (t * 1000), MediaPlayer.SEEK_CLOSEST_SYNC);
            }
            m.start();
            spin.setVisibility(View.GONE);
        });
        mp.setOnInfoListener((m, what, extra) -> {
            if (what == MediaPlayer.MEDIA_INFO_BUFFERING_START) spin.setVisibility(View.VISIBLE);
            if (what == MediaPlayer.MEDIA_INFO_BUFFERING_END || what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) spin.setVisibility(View.GONE);
            return false;
        });
        mp.setOnCompletionListener(m -> ended());
        mp.setOnErrorListener((m, what, extra) -> { onError(what + "/" + extra); return true; });
        mp.prepareAsync();
    }

    private void selectAudio(MediaPlayer m) {
        try {
            int want = info.optInt("audio_sel", -1);
            JSONArray au = info.optJSONArray("audio");
            if (want < 0 || au == null || au.length() < 2) return;
            int ord = 0;
            for (int i = 0; i < au.length(); i++) if (au.optJSONObject(i).optInt("i") == want) ord = i;
            MediaPlayer.TrackInfo[] ti = m.getTrackInfo();
            int n = 0;
            for (int i = 0; i < ti.length; i++) {
                if (ti[i].getTrackType() == MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_AUDIO) {
                    if (n == ord) { m.selectTrack(i); return; }
                    n++;
                }
            }
        } catch (Exception ignored) { }
    }

    private void layoutVideo() {
        if (vw <= 0 || vh <= 0) return;
        int W = root.getWidth(), H = root.getHeight();
        if (W == 0 || H == 0) return;
        float r = Math.min(W / (float) vw, H / (float) vh);
        surface.setLayoutParams(new FrameLayout.LayoutParams((int) (vw * r), (int) (vh * r), Gravity.CENTER));
    }

    private void onError(String what) {
        if (closing) return;
        if (liveId > 0) {
            if (liveMode.equals("copy")) { liveMode = "transcode"; Ui.toast(this, "Sender wird umgewandelt …"); startLive(liveId); }
            else fail("Sender nicht erreichbar (" + what + ")");
            return;
        }
        if (info == null) { fail(what); return; }
        double t = cur();
        String mode = info.optString("mode");
        Integer a = info.isNull("audio_sel") ? null : info.optInt("audio_sel");
        String s = info.isNull("sub_sel") ? null : info.optString("sub_sel");
        if (mode.equals("direct") && fallback < 1) { fallback = 1; Ui.toast(this, "Direktwiedergabe nicht möglich – Remux"); start(itemId, t, a, s, height, "remux"); }
        else if (!mode.equals("transcode") && fallback < 2) { fallback = 2; Ui.toast(this, "Wird umgewandelt …"); start(itemId, t, a, s, height, "transcode"); }
        else fail("Wiedergabe fehlgeschlagen (" + what + ")");
    }

    private void fail(String msg) {
        spin.setVisibility(View.GONE);
        new AlertDialog.Builder(this).setTitle("Wiedergabe nicht möglich").setMessage(msg.replaceFirst("^401:", ""))
                .setPositiveButton("Schließen", (d, w) -> finish()).setOnCancelListener(d -> finish()).show();
    }

    // ------------------------------------------------------------ Zeit / Spulen
    private double cur() {
        if (mp == null || !prepared) return offset;
        try { return offset + mp.getCurrentPosition() / 1000.0; } catch (Exception e) { return offset; }
    }

    private double dur() {
        double d = info != null ? info.optDouble("duration", 0) : 0;
        if (d <= 0 && mp != null && prepared) try { d = mp.getDuration() / 1000.0; } catch (Exception ignored) { }
        return d;
    }

    private final Runnable doSeek = () -> {
        double t = pendingSeek;
        pendingSeek = -1;
        if (t < 0 || info == null) return;
        if ("direct".equals(info.optString("mode")) && mp != null && prepared) mp.seekTo((long) (t * 1000), MediaPlayer.SEEK_CLOSEST_SYNC);
        else setSource(t);
    };

    private void skip(double by) {
        if (info == null || liveId > 0) return;
        double base = pendingSeek >= 0 ? pendingSeek : cur();
        pendingSeek = Math.max(0, Math.min(base + by, dur() - 3));
        showOverlay();
        h.removeCallbacks(doSeek);
        h.postDelayed(doSeek, 800);
        update();
    }

    private void seekAbs(double t) { pendingSeek = Math.max(0, t); h.removeCallbacks(doSeek); doSeek.run(); }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            update();
            if (mp != null && prepared && info != null && liveId == 0) {
                try {
                    if (mp.isPlaying() && Math.abs(cur() - lastRep) > 10) report("playing");
                } catch (Exception ignored) { }
            }
            h.postDelayed(this, 250);
        }
    };

    private void update() {
        if (info == null && liveId == 0) return;
        double t = pendingSeek >= 0 ? pendingSeek : cur(), d = dur();
        seek.set(d > 0 ? t / d : 0, info != null ? info.optJSONArray("markers") : null, d);
        if (liveId == 0) {
            tTime.setText(Ui.fmtT(t) + " / " + Ui.fmtT(d));
            if (d > 0) tEnd.setText("Ende " + MainActivity.hm(System.currentTimeMillis() / 1000.0 + (d - t)));
        }
        // Untertitel
        String txt = "";
        for (int i = 0; i < cueT.size(); i++) {
            double[] c = cueT.get(i);
            if (t >= c[0] && t <= c[1]) txt = txt.isEmpty() ? cueX.get(i) : txt + "\n" + cueX.get(i);
        }
        if (!txt.contentEquals(tCue.getText())) tCue.setText(txt);
        if (info != null && liveId == 0) markers(t, d);
    }

    private void markers(double t, double d) {
        JSONArray m = info.optJSONArray("markers");
        JSONObject intro = null, cred = null;
        for (int i = 0; m != null && i < m.length(); i++) {
            JSONObject x = m.optJSONObject(i);
            if ("intro".equals(x.optString("type")) && t >= x.optDouble("start") && t < x.optDouble("end") - 1) intro = x;
            if ("credits".equals(x.optString("type"))) cred = x;
        }
        JSONObject next = tvId > 0 ? null : info.optJSONObject("next");
        double from = cred != null ? cred.optDouble("start") : d - 25;
        if (intro != null) {
            final double end = intro.optDouble("end");
            showAction("Intro überspringen", v -> seekAbs(end));
        } else if (next != null && d > 0 && t >= from && t < d - 1 && !nuDismissed) {
            if (actionBtn.getVisibility() != View.VISIBLE) nuAt = System.currentTimeMillis();
            int left = 15 - (int) ((System.currentTimeMillis() - nuAt) / 1000);
            boolean auto = App.api.prefBool("autoplay", true) && cred != null;
            showAction("Nächste Folge ▶  S" + next.optInt("season") + "·F" + next.optInt("episode") + (auto ? "  (" + Math.max(0, left) + ")" : ""), v -> playNext());
            if (auto && left <= 0) playNext();
        } else if (actionBtn.getVisibility() == View.VISIBLE) actionBtn.setVisibility(View.GONE);
    }

    private void showAction(String label, View.OnClickListener l) {
        actionBtn.setText(label);
        actionBtn.setOnClickListener(l);
        if (actionBtn.getVisibility() != View.VISIBLE) {
            actionBtn.setVisibility(View.VISIBLE);
            actionBtn.requestFocus();
        }
    }

    private void playNext() {
        JSONObject n = info != null ? info.optJSONObject("next") : null;
        if (n == null) { finish(); return; }
        report("stopped");
        fallback = 0;
        start(n.optInt("id"), 0, null, null, height, null);
    }

    private void ended() {
        if (liveId > 0) { onError("Ende"); return; }
        report("stopped");
        if (tvId > 0) { tuneNow(); return; }
        if (info != null && info.optJSONObject("next") != null && App.api.prefBool("autoplay", true)) playNext();
        else finish();
    }

    private void report(String state) {
        if (info == null || liveId > 0) return;
        double t = cur();
        lastRep = t;
        App.api.post("/api/progress", Api.obj("id", itemId, "pos", t, "dur", dur(), "play", info.optInt("play"), "state", state, "tv", tvId > 0), null);
    }

    // ------------------------------------------------------------ Untertitel (eigener VTT-Leser)
    private void loadSubs(String key) {
        cueT.clear();
        cueX.clear();
        tCue.setText("");
        if (key == null || key.isEmpty() || info == null) return;
        int id = itemId;
        Api.POOL.execute(() -> {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(App.api.url("/api/sub/" + id + "/" + key + ".vtt")).openConnection();
                c.setRequestProperty("X-Token", App.api.token());
                c.setReadTimeout(300000);
                if (c.getResponseCode() != 200) throw new Exception("HTTP " + c.getResponseCode());
                String txt = Api.read(c.getInputStream());
                List<double[]> ts = new ArrayList<>();
                List<String> xs = new ArrayList<>();
                for (String block : txt.replace("\r", "").split("\n\n+")) {
                    String[] lines = block.split("\n");
                    int i = 0;
                    while (i < lines.length && !lines[i].contains("-->")) i++;
                    if (i >= lines.length) continue;
                    String[] ab = lines[i].split("-->");
                    StringBuilder sb = new StringBuilder();
                    for (int j = i + 1; j < lines.length; j++) sb.append(j > i + 1 ? "\n" : "").append(lines[j]);
                    String x = sb.toString().replaceAll("<[^>]+>", "").replaceAll("\\{\\\\[^}]*\\}", "").trim();
                    if (x.isEmpty()) continue;
                    ts.add(new double[]{vtt(ab[0]), vtt(ab[1].trim().split(" ")[0])});
                    xs.add(x);
                }
                h.post(() -> { if (id == itemId) { cueT.clear(); cueX.clear(); cueT.addAll(ts); cueX.addAll(xs); applySubStyle(); } });
            } catch (Exception e) {
                h.post(() -> Ui.toast(this, "Untertitel nicht lesbar"));
            }
        });
    }

    private static double vtt(String s) {
        String[] p = s.trim().replace(',', '.').split(":");
        double v = 0;
        for (String x : p) v = v * 60 + Double.parseDouble(x);
        return v;
    }

    private void applySubStyle() {
        tCue.setTextSize(30 * subScale() * Ui.scale);
        if (App.api.prefInt("sub_bg", 0) == 1) { tCue.setBackgroundColor(0xbb000000); tCue.setShadowLayer(0, 0, 0, 0); }
        else { tCue.setBackground(null); tCue.setShadowLayer(6, 2, 2, 0xff000000); }
    }

    // ------------------------------------------------------------ Menü Ton / Untertitel / Qualität
    private void options() {
        if (info == null) return;
        String[] items = {"Tonspur", "Untertitel", "Qualität", "Untertitelgröße"};
        new AlertDialog.Builder(this).setItems(items, (d, w) -> {
            if (w == 0) audioMenu();
            else if (w == 1) subMenu();
            else if (w == 2) qualityMenu();
            else sizeMenu();
        }).show();
    }

    private void audioMenu() {
        JSONArray au = info.optJSONArray("audio");
        if (au == null || au.length() == 0) return;
        String[] n = new String[au.length()];
        int sel = 0;
        for (int i = 0; i < au.length(); i++) {
            JSONObject x = au.optJSONObject(i);
            n[i] = Ui.lang(x.optString("lang")) + " · " + Ui.codec(x.optString("codec")) + " " + Ui.channels(x.optInt("channels")) + (x.optString("title").isEmpty() ? "" : " · " + x.optString("title"));
            if (x.optInt("i") == info.optInt("audio_sel", -1)) sel = i;
        }
        new AlertDialog.Builder(this).setTitle("Tonspur").setSingleChoiceItems(n, sel, (d, w) -> {
            d.dismiss();
            start(itemId, cur(), au.optJSONObject(w).optInt("i"), curSub(), height, null);
        }).show();
    }

    private String curSub() {
        if (!info.isNull("burn")) return "i" + info.optInt("burn");
        return info.isNull("sub_sel") ? "" : info.optString("sub_sel");
    }

    private void subMenu() {
        JSONArray s = info.optJSONArray("subs");
        int n = s == null ? 0 : s.length();
        String[] names = new String[n + 1];
        names[0] = "Aus";
        String now = curSub();
        int sel = 0;
        for (int i = 0; i < n; i++) {
            JSONObject x = s.optJSONObject(i);
            names[i + 1] = Ui.lang(x.optString("lang")) + (x.optBoolean("forced") ? " (erzwungen)" : "") + " · " + Ui.codec(x.optString("codec")) + (x.optBoolean("text") ? "" : " – wird eingebrannt");
            if (x.optString("key").equals(now)) sel = i + 1;
        }
        new AlertDialog.Builder(this).setTitle("Untertitel").setSingleChoiceItems(names, sel, (d, w) -> {
            d.dismiss();
            JSONObject x = w == 0 ? null : s.optJSONObject(w - 1);
            boolean burnNow = !info.isNull("burn");
            Integer a = info.isNull("audio_sel") ? null : info.optInt("audio_sel");
            if ((x != null && !x.optBoolean("text")) || burnNow) start(itemId, cur(), a, x == null ? "" : x.optString("key"), height, null);
            else {
                try { info.put("sub_sel", x == null ? JSONObject.NULL : x.optString("key")); } catch (Exception ignored) { }
                loadSubs(x == null ? null : x.optString("key"));
            }
        }).show();
    }

    private void qualityMenu() {
        int[] q = {0, 1080, 720, 480, 360};
        String[] n = {"Original", "1080p", "720p", "480p", "360p"};
        int sel = 0;
        for (int i = 0; i < q.length; i++) if (height != null && height == q[i]) sel = i;
        new AlertDialog.Builder(this).setTitle("Qualität").setSingleChoiceItems(n, sel, (d, w) -> {
            d.dismiss();
            Integer a = info.isNull("audio_sel") ? null : info.optInt("audio_sel");
            start(itemId, cur(), a, curSub(), q[w] == 0 ? null : q[w], q[w] == 0 ? null : "transcode");
        }).show();
    }

    private void sizeMenu() {
        int[] z = {75, 100, 125, 150};
        String[] n = {"Klein", "Normal", "Groß", "Sehr groß"};
        new AlertDialog.Builder(this).setTitle("Untertitelgröße").setItems(n, (d, w) -> {
            try { App.api.prefs.put("sub_size", z[w]); } catch (Exception ignored) { }
            App.api.put("/api/me/prefs", Api.obj("sub_size", z[w]), null);
            applySubStyle();
        }).show();
    }

    // ------------------------------------------------------------ Sender / Live-TV
    private void tuneNow() {
        App.api.get("/api/channels/" + tvId + "/tune", (r, e) -> {
            if (e != null) { fail(e); return; }
            JSONObject t = Api.o(r);
            fallback = 0;
            start(t.optInt("item"), t.optDouble("offset"), null, null, null, null);
        });
    }

    private void startLive(int cid) {
        liveId = cid;
        info = null;
        offset = 0;
        String name = "";
        for (int i = 0; liveIds != null && i < liveIds.length; i++) if (liveIds[i] == cid) name = liveNames[i];
        tTitle.setText(name);
        tSub.setText("");
        tInfo.setText(liveMode.equals("copy") ? "Live" : "Live · umgewandelt");
        tTime.setText("Kanal ↑/↓ wechseln");
        tEnd.setText("");
        App.api.get("/api/live/epg?id=" + cid + "&from=" + (System.currentTimeMillis() / 1000) + "&to=" + (System.currentTimeMillis() / 1000 + 4 * 3600), (r, e) -> {
            JSONArray l = Api.o(r).optJSONArray(String.valueOf(cid));
            if (l != null && l.length() > 0) {
                JSONObject p = l.optJSONObject(0);
                tSub.setText(MainActivity.hm(p.optDouble("start")) + "–" + MainActivity.hm(p.optDouble("stop")) + "  " + p.optString("title"));
                if (l.length() > 1) tEnd.setText("Danach " + MainActivity.hm(l.optJSONObject(1).optDouble("start")) + ": " + l.optJSONObject(1).optString("title"));
            }
        });
        release();
        prepared = false;
        spin.setVisibility(View.VISIBLE);
        mp = new MediaPlayer();
        try {
            mp.setDataSource(this, Uri.parse(App.api.url("/api/live/" + cid + "/stream?mode=" + liveMode)), App.api.headers());
        } catch (Exception e) { fail(e.toString()); return; }
        mp.setDisplay(holder);
        mp.setOnVideoSizeChangedListener((m, w, hh) -> { vw = w; vh = hh; layoutVideo(); });
        mp.setOnPreparedListener(m -> { prepared = true; m.start(); spin.setVisibility(View.GONE); });
        mp.setOnInfoListener((m, what, extra) -> {
            if (what == MediaPlayer.MEDIA_INFO_BUFFERING_START) spin.setVisibility(View.VISIBLE);
            if (what == MediaPlayer.MEDIA_INFO_BUFFERING_END || what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) spin.setVisibility(View.GONE);
            return false;
        });
        mp.setOnCompletionListener(m -> startLive(liveId));
        mp.setOnErrorListener((m, what, extra) -> { onError(what + "/" + extra); return true; });
        mp.prepareAsync();
        showOverlay();
    }

    private void zap(int d) {
        if (liveIds == null || liveIds.length == 0) return;
        int i = 0;
        for (int k = 0; k < liveIds.length; k++) if (liveIds[k] == liveId) i = k;
        liveMode = "copy";
        startLive(liveIds[(i + d + liveIds.length) % liveIds.length]);
    }

    // ------------------------------------------------------------ Bedienung
    private final Runnable hide = () -> { if (mp != null && prepared && isPlaying()) overlay.setVisibility(View.GONE); };

    private boolean isPlaying() { try { return mp.isPlaying(); } catch (Exception e) { return false; } }

    private void showOverlay() {
        overlay.setVisibility(View.VISIBLE);
        h.removeCallbacks(hide);
        h.postDelayed(hide, 4000);
    }

    private void togglePause() {
        if (mp == null || !prepared) return;
        if (isPlaying()) { mp.pause(); report("paused"); overlay.setVisibility(View.VISIBLE); h.removeCallbacks(hide); }
        else { mp.start(); showOverlay(); }
    }

    @Override public boolean dispatchKeyEvent(KeyEvent ev) {
        int k = ev.getKeyCode();
        if (ev.getAction() != KeyEvent.ACTION_DOWN) return super.dispatchKeyEvent(ev);
        boolean btn = actionBtn.getVisibility() == View.VISIBLE && actionBtn.hasFocus();
        switch (k) {
            case KeyEvent.KEYCODE_DPAD_CENTER: case KeyEvent.KEYCODE_ENTER:
                if (btn) return super.dispatchKeyEvent(ev);
                if (liveId > 0) { showOverlay(); return true; }
                togglePause(); return true;
            case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE: case KeyEvent.KEYCODE_MEDIA_PLAY: case KeyEvent.KEYCODE_MEDIA_PAUSE:
                togglePause(); return true;
            case KeyEvent.KEYCODE_DPAD_LEFT: case KeyEvent.KEYCODE_MEDIA_REWIND:
                if (btn && k == KeyEvent.KEYCODE_DPAD_LEFT) { nuDismissed = true; actionBtn.setVisibility(View.GONE); }
                skip(-App.api.prefInt("skip_back", 10)); return true;
            case KeyEvent.KEYCODE_DPAD_RIGHT: case KeyEvent.KEYCODE_MEDIA_FAST_FORWARD:
                skip(App.api.prefInt("skip_fwd", 30)); return true;
            case KeyEvent.KEYCODE_DPAD_UP: case KeyEvent.KEYCODE_CHANNEL_UP:
                if (liveId > 0) { zap(-1); return true; }
                if (k == KeyEvent.KEYCODE_DPAD_UP) { options(); return true; }
                return true;
            case KeyEvent.KEYCODE_DPAD_DOWN: case KeyEvent.KEYCODE_CHANNEL_DOWN:
                if (liveId > 0) { zap(1); return true; }
                if (btn) return true;
                showOverlay(); return true;
            case KeyEvent.KEYCODE_MENU: case KeyEvent.KEYCODE_INFO:
                options(); return true;
            case KeyEvent.KEYCODE_MEDIA_NEXT:
                if (info != null && info.optJSONObject("next") != null && tvId == 0) playNext(); return true;
            case KeyEvent.KEYCODE_BACK:
                if (overlay.getVisibility() == View.VISIBLE && isPlaying()) { overlay.setVisibility(View.GONE); return true; }
                finish(); return true;
        }
        return super.dispatchKeyEvent(ev);
    }

    @Override protected void onPause() {
        super.onPause();
        if (mp != null && prepared && isPlaying() && !isFinishing()) { report("paused"); mp.pause(); }
    }

    @Override public void finish() {
        if (!closing) { closing = true; report("stopped"); }
        super.finish();
    }

    @Override protected void onDestroy() {
        closing = true;
        h.removeCallbacksAndMessages(null);
        release();
        super.onDestroy();
    }

    private void release() {
        if (mp != null) {
            try { mp.reset(); mp.release(); } catch (Exception ignored) { }
            mp = null;
        }
    }

    /** Fortschrittsbalken mit Marken für Intro/Abspann. */
    static class SeekView extends View {
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private double f;
        private JSONArray marks;
        private double dur;

        SeekView(Context c) { super(c); }

        void set(double frac, JSONArray m, double d) {
            if (frac == f && m == marks) return;
            f = Math.max(0, Math.min(1, frac));
            marks = m;
            dur = d;
            invalidate();
        }

        @Override protected void onDraw(Canvas c) {
            float w = getWidth(), hh = getHeight(), y = hh / 2, th = hh / 4f;
            p.setColor(0x44ffffff);
            c.drawRoundRect(0, y - th / 2, w, y + th / 2, th, th, p);
            p.setColor(0xccfcd34d);
            for (int i = 0; marks != null && dur > 0 && i < marks.length(); i++) {
                JSONObject m = marks.optJSONObject(i);
                float a = (float) (m.optDouble("start") / dur * w), b = (float) (m.optDouble("end", dur) / dur * w);
                c.drawRect(a, y - th / 2, Math.max(a + 3, b), y + th / 2, p);
            }
            p.setColor(Ui.ACC);
            c.drawRoundRect(0, y - th / 2, (float) (w * f), y + th / 2, th, th, p);
            p.setColor(0xffffffff);
            c.drawCircle((float) (w * f), y, hh / 2.4f, p);
        }
    }

    static String clock() { return MainActivity.hm(new Date().getTime() / 1000.0); }
}
