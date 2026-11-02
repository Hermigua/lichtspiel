package de.lichtspiel.tv;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.Locale;

/** Gemeinsame Bausteine der Oberfläche (alles per Code, keine Fremdbibliothek). */
public final class Ui {
    public static final int BG = 0xff0d1117, BG2 = 0xff141a22, BG3 = 0xff1c2430, LINE = 0xff263041,
            FG = 0xffe8edf3, DIM = 0xff93a1b3, ACC = 0xff2ec4b6, ACC2 = 0xfffcd34d, OK = 0xff22c55e;

    public static float scale = 1f; // Darstellungsgröße (Einstellungen)

    public static int dp(Context c, float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v * scale, c.getResources().getDisplayMetrics()));
    }

    public static TextView text(Context c, String s, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp * scale);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return t;
    }

    public static GradientDrawable round(int color, float radiusDp, Context c) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(c, radiusDp));
        return g;
    }

    public static GradientDrawable roundStroke(int color, int stroke, float radiusDp, Context c) {
        GradientDrawable g = round(color, radiusDp, c);
        g.setStroke(dp(c, 3), stroke);
        return g;
    }

    /** Knopf im TV-Stil: Fokus = Akzentfarbe. */
    public static TextView button(Context c, String label, View.OnClickListener l) {
        TextView b = text(c, label, 17, FG, true);
        b.setFocusable(true);
        b.setClickable(true);
        b.setGravity(Gravity.CENTER);
        int px = dp(c, 20), py = dp(c, 10);
        b.setPadding(px, py, px, py);
        b.setBackground(round(BG3, 10, c));
        b.setOnFocusChangeListener((v, f) -> {
            v.setBackground(round(f ? ACC : BG3, 10, c));
            ((TextView) v).setTextColor(f ? 0xff04201e : FG);
        });
        b.setOnClickListener(l);
        return b;
    }

    public static LinearLayout.LayoutParams lp(int w, int h) { return new LinearLayout.LayoutParams(w, h); }
    public static final int MATCH = ViewGroup.LayoutParams.MATCH_PARENT, WRAP = ViewGroup.LayoutParams.WRAP_CONTENT;

    public static LinearLayout.LayoutParams margins(LinearLayout.LayoutParams p, Context c, int l, int t, int r, int b) {
        p.setMargins(dp(c, l), dp(c, t), dp(c, r), dp(c, b));
        return p;
    }

    /** Karte (Hochformat-Cover oder Breitbild) für Filme, Serien, Staffeln, Folgen. */
    public static View card(Activity a, JSONObject it, boolean wide, View.OnClickListener click) {
        int w = dp(a, wide ? 300 : 160), h = wide ? w * 9 / 16 : w * 3 / 2;
        LinearLayout box = new LinearLayout(a);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setFocusable(true);
        box.setClickable(true);
        box.setPadding(dp(a, 6), dp(a, 6), dp(a, 6), dp(a, 6));
        FrameLayout pic = new FrameLayout(a);
        pic.setBackground(round(BG3, 8, a));
        pic.setClipToOutline(true);
        String title = it.optString("title");
        String kind = it.optString("kind");
        String sub = "";
        if (kind.equals("episode")) {
            title = it.optString("show_title", title);
            sub = "S" + it.optInt("season") + " · F" + it.optInt("episode") + " – " + it.optString("title");
        } else if (kind.equals("season")) {
            sub = it.has("total") ? it.optInt("total") + " Folgen" : "";
        } else if (it.optInt("year") > 0) sub = String.valueOf(it.optInt("year"));
        TextView ph = text(a, title, 15, DIM, true);
        ph.setGravity(Gravity.CENTER);
        ph.setPadding(dp(a, 8), 0, dp(a, 8), 0);
        pic.addView(ph, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
        ImageView iv = new ImageView(a);
        iv.setScaleType(ImageView.ScaleType.CENTER_CROP);
        pic.addView(iv, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
        int id = it.optInt("id");
        String img;
        if (wide) img = kind.equals("episode") ? "/api/img/" + id + "/thumb?w=480" : "/api/img/" + id + "/backdrop?w=480";
        else img = kind.equals("episode") ? "/api/img/" + id + "/cover?w=300" : "/api/img/" + id + "/poster?w=300";
        if (it.has("img")) img = it.optString("img");
        Img.load(iv, App.api.url(img));
        // Fortschritt und Abzeichen
        double pos = it.optDouble("pos", 0), dur = it.optDouble("duration", 0);
        if (pos > 0 && dur > 0) {
            View track = new View(a);
            track.setBackgroundColor(0x99000000);
            FrameLayout.LayoutParams tp = new FrameLayout.LayoutParams(Ui.MATCH, dp(a, 5), Gravity.BOTTOM);
            pic.addView(track, tp);
            View bar = new View(a);
            bar.setBackgroundColor(ACC);
            pic.addView(bar, new FrameLayout.LayoutParams((int) (w * Math.min(1, pos / dur)), dp(a, 5), Gravity.BOTTOM));
        }
        String badge = null;
        boolean ok = false;
        if (it.optInt("unwatched", -1) > 0) badge = String.valueOf(it.optInt("unwatched"));
        else if (it.optBoolean("watched") || (it.optInt("unwatched", -1) == 0 && it.optInt("total") > 0)) { badge = "✓"; ok = true; }
        if (it.has("badge")) badge = it.optString("badge");
        if (badge != null) {
            TextView b = text(a, badge, 13, ok ? OK : 0xff062a27, true);
            b.setGravity(Gravity.CENTER);
            b.setPadding(dp(a, 8), dp(a, 2), dp(a, 8), dp(a, 2));
            b.setMinWidth(dp(a, 26));
            b.setBackground(ok ? roundStroke(0xcc0b1f12, OK, 13, a) : round(ACC, 13, a));
            FrameLayout.LayoutParams bp = new FrameLayout.LayoutParams(Ui.WRAP, Ui.WRAP, Gravity.TOP | Gravity.END);
            bp.setMargins(0, dp(a, 6), dp(a, 6), 0);
            pic.addView(b, bp);
        }
        box.addView(pic, lp(w, h));
        TextView t = text(a, title, 15, FG, true);
        t.setMaxWidth(w);
        box.addView(t, margins(lp(w, WRAP), a, 0, 6, 0, 0));
        if (!sub.isEmpty()) {
            TextView s = text(a, sub, 13, DIM, false);
            s.setMaxWidth(w);
            box.addView(s, lp(w, WRAP));
        }
        box.setOnFocusChangeListener((v, f) -> hi(v, f));
        box.setOnClickListener(click);
        return box;
    }

    /** Hervorhebung einer Karte (Fokus bzw. Auswahl im Raster). */
    public static void hi(View v, boolean f) {
        if (v == null) return;
        v.animate().scaleX(f ? 1.06f : 1f).scaleY(f ? 1.06f : 1f).setDuration(120).start();
        View pic = ((ViewGroup) v).getChildAt(0);
        pic.setForeground(f ? roundStroke(Color.TRANSPARENT, ACC, 8, v.getContext()) : null);
        v.setElevation(f ? dp(v.getContext(), 8) : 0);
    }

    public static void openItem(Activity a, int id) {
        a.startActivity(new Intent(a, DetailActivity.class).putExtra("id", id));
    }

    public static void toast(Context c, String s) { Toast.makeText(c, s, Toast.LENGTH_LONG).show(); }

    public static String fmtT(double s) {
        long x = Math.max(0, (long) s), h = x / 3600, m = x % 3600 / 60, sec = x % 60;
        return h > 0 ? String.format(Locale.GERMANY, "%d:%02d:%02d", h, m, sec) : String.format(Locale.GERMANY, "%d:%02d", m, sec);
    }

    public static String fmtDur(double s) {
        long m = Math.round(s / 60);
        if (m <= 0) return "";
        return m >= 60 ? (m / 60) + " Std. " + (m % 60) + " Min." : m + " Min.";
    }

    public static String lang(String l) {
        if (l == null) return "Unbekannt";
        switch (l.toLowerCase(Locale.ROOT)) {
            case "deu": case "ger": case "de": return "Deutsch";
            case "eng": case "en": return "Englisch";
            case "fra": case "fre": case "fr": return "Französisch";
            case "spa": case "es": return "Spanisch";
            case "ita": case "it": return "Italienisch";
            case "jpn": return "Japanisch";
            case "tur": return "Türkisch";
            case "": case "und": return "Unbekannt";
            default: return l.toUpperCase(Locale.ROOT);
        }
    }

    public static String codec(String c) {
        if (c == null) return "";
        switch (c) {
            case "h264": return "H.264"; case "hevc": return "HEVC"; case "aac": return "AAC"; case "ac3": return "Dolby Digital";
            case "eac3": return "Dolby Digital+"; case "dts": return "DTS"; case "truehd": return "TrueHD"; case "subrip": return "SRT";
            case "hdmv_pgs_subtitle": return "PGS (Bild)"; case "dvd_subtitle": return "VobSub (Bild)";
            default: return c.toUpperCase(Locale.ROOT);
        }
    }

    public static String channels(int n) {
        switch (n) { case 1: return "Mono"; case 2: return "Stereo"; case 6: return "5.1"; case 8: return "7.1"; default: return n > 0 ? n + " Kan." : ""; }
    }

    public static boolean empty(String s) { return TextUtils.isEmpty(s); }
}
