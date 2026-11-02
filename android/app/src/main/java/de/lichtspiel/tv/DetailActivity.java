package de.lichtspiel.tv;

import android.app.Activity;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Locale;

/** Detailseite für Film, Serie, Staffel oder Folge. */
public class DetailActivity extends Activity {
    private int id;
    private FrameLayout root;
    private boolean first = true;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        id = getIntent().getIntExtra("id", 0);
        root = new FrameLayout(this);
        root.setBackgroundColor(Ui.BG);
        setContentView(root);
    }

    @Override protected void onResume() {
        super.onResume();
        load();
    }

    private void load() {
        App.api.get("/api/item/" + id, (r, e) -> {
            if (e != null) { Ui.toast(this, e); finish(); return; }
            render(Api.o(r));
        });
    }

    private void render(JSONObject it) {
        View keep = getCurrentFocus();
        Object keepTag = keep != null ? keep.getTag() : null;
        root.removeAllViews();
        String kind = it.optString("kind");
        ImageView bd = new ImageView(this);
        bd.setScaleType(ImageView.ScaleType.CENTER_CROP);
        bd.setAlpha(0.45f);
        Img.load(bd, App.api.url("/api/img/" + id + "/backdrop?w=1280"));
        root.addView(bd, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
        View shade = new View(this);
        shade.setBackground(new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{0xf20d1117, 0xcc0d1117, 0x550d1117}));
        root.addView(shade, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));

        ScrollView sv = new ScrollView(this);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(Ui.dp(this, 48), Ui.dp(this, 36), Ui.dp(this, 48), Ui.dp(this, 40));
        sv.addView(col);
        root.addView(sv);

        LinearLayout top = new LinearLayout(this);
        boolean wide = kind.equals("episode");
        FrameLayout pf = new FrameLayout(this);
        pf.setBackground(Ui.round(Ui.BG3, 10, this));
        pf.setClipToOutline(true);
        ImageView poster = new ImageView(this);
        poster.setScaleType(ImageView.ScaleType.CENTER_CROP);
        pf.addView(poster, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
        Img.load(poster, App.api.url("/api/img/" + id + (wide ? "/thumb?w=720" : "/poster?w=440")));
        int pw = Ui.dp(this, wide ? 340 : 220);
        top.addView(pf, Ui.lp(pw, wide ? pw * 9 / 16 : pw * 3 / 2));
        LinearLayout info = new LinearLayout(this);
        info.setOrientation(LinearLayout.VERTICAL);
        info.setPadding(Ui.dp(this, 32), 0, 0, 0);
        top.addView(info, new LinearLayout.LayoutParams(0, Ui.WRAP, 1));
        col.addView(top);

        if (kind.equals("episode") || kind.equals("season"))
            info.addView(Ui.text(this, it.optString("show_title"), 20, Ui.DIM, false));
        boolean logo = it.optBoolean("has_logo") && (kind.equals("movie") || kind.equals("show"));
        if (logo) {
            ImageView lg = new ImageView(this);
            lg.setAdjustViewBounds(true);
            lg.setScaleType(ImageView.ScaleType.FIT_START);
            lg.setContentDescription(it.optString("title"));
            Img.load(lg, App.api.url("/api/img/" + id + "/logo?w=800"));
            info.addView(lg, Ui.lp(Ui.dp(this, 420), Ui.dp(this, 120)));
        } else info.addView(Ui.text(this, it.optString("title"), 32, Ui.FG, true));
        StringBuilder meta = new StringBuilder();
        if (kind.equals("episode")) meta.append("Staffel ").append(it.optInt("season")).append(" · Folge ").append(it.optInt("episode")).append("   ");
        if (it.optInt("year") > 0) meta.append(it.optInt("year")).append("   ");
        if (it.optDouble("duration", 0) > 0) meta.append(Ui.fmtDur(it.optDouble("duration"))).append("   ");
        if (!it.optString("mpaa").isEmpty() && !it.isNull("mpaa")) meta.append(it.optString("mpaa")).append("   ");
        if (it.optDouble("rating", 0) > 0) meta.append("★ ").append(String.format(Locale.GERMANY, "%.1f", it.optDouble("rating"))).append("   ");
        JSONArray kids = it.optJSONArray("children");
        if (kind.equals("show") && kids != null) meta.append(kids.length()).append(kids.length() == 1 ? " Staffel" : " Staffeln");
        info.addView(Ui.text(this, meta.toString().trim(), 17, Ui.DIM, false), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 8, 0, 4));
        JSONArray g = it.optJSONArray("genres");
        if (g != null && g.length() > 0) {
            StringBuilder gs = new StringBuilder();
            for (int i = 0; i < g.length(); i++) gs.append(i > 0 ? " · " : "").append(g.optString(i));
            info.addView(Ui.text(this, gs.toString(), 16, Ui.DIM, false));
        }
        // Knöpfe
        LinearLayout btns = new LinearLayout(this);
        boolean playable = kind.equals("movie") || kind.equals("episode");
        JSONObject target = playable ? it : it.optJSONObject("play");
        double pos = 0;
        String lbl = "▶  Abspielen";
        if (playable && it.optDouble("pos", 0) > 0 && !it.optBoolean("watched")) { pos = it.optDouble("pos"); lbl = "▶  Fortsetzen ab " + Ui.fmtT(pos); }
        if (!playable && target != null) {
            pos = target.optDouble("pos", 0);
            lbl = (pos > 0 ? "▶  Fortsetzen " : "▶  Abspielen ") + "S" + target.optInt("season") + " · F" + target.optInt("episode");
        }
        TextView play = null;
        if (target != null) {
            final double p0 = pos;
            final int tid = target.optInt("id");
            play = Ui.button(this, lbl, v -> PlayerActivity.play(this, tid, p0));
            play.setTag("play");
            btns.addView(play, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 12, 0));
            if (pos > 0) {
                TextView rs = Ui.button(this, "Von Anfang an", v -> PlayerActivity.play(this, tid, 0));
                rs.setTag("restart");
                btns.addView(rs, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 12, 0));
            }
        }
        boolean watched = playable ? it.optBoolean("watched") : it.optInt("unwatched", 1) == 0;
        TextView w = Ui.button(this, watched ? "✓  Gesehen" : "Als gesehen markieren", v ->
                App.api.post("/api/watched/" + id, Api.obj("watched", !watched), (r, e) -> load()));
        w.setTag("watched");
        btns.addView(w, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 12, 0));
        boolean fav = it.optBoolean("fav");
        TextView fv = Ui.button(this, fav ? "♥ Favorit" : "♡ Favorit", v ->
                App.api.post("/api/fav/" + id, Api.obj("on", !fav), (r, e) -> load()));
        fv.setTag("fav");
        btns.addView(fv);
        info.addView(btns, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 18, 0, 14));
        TextView plot = Ui.text(this, it.optString("plot"), 18, 0xffd3dbe5, false);
        plot.setLineSpacing(0, 1.25f);
        info.addView(plot);

        // Staffeln / Folgen / Besetzung
        if (kind.equals("show") && kids != null) {
            col.addView(Ui.text(this, "Staffeln", 21, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 28, 0, 6));
            col.addView(row(kids, false));
        }
        if (kind.equals("season") && kids != null) {
            col.addView(Ui.text(this, kids.length() + " Folgen", 21, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 28, 0, 6));
            for (int i = 0; i < kids.length(); i++) col.addView(episodeRow(kids.optJSONObject(i)));
        }
        if (kind.equals("episode")) {
            LinearLayout nav = new LinearLayout(this);
            if (!it.isNull("prev") && it.optInt("prev") > 0) nav.addView(Ui.button(this, "← Vorherige Folge", v -> { id = it.optInt("prev"); load(); }), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 12, 0));
            JSONObject n = it.optJSONObject("next");
            if (n != null) nav.addView(Ui.button(this, "Nächste: S" + n.optInt("season") + "·F" + n.optInt("episode") + " " + n.optString("title") + " →", v -> { id = n.optInt("id"); load(); }), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 12, 0));
            col.addView(nav, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 24, 0, 0));
        }
        JSONArray ppl = it.optJSONArray("people");
        if (ppl != null && ppl.length() > 0) {
            LinearLayout pr = new LinearLayout(this);
            int ref = kind.equals("episode") || kind.equals("season") ? it.optInt("show_id") : id;
            for (int i = 0; i < ppl.length(); i++) {
                JSONObject p = ppl.optJSONObject(i);
                if (!"actor".equals(p.optString("type"))) continue;
                LinearLayout one = new LinearLayout(this);
                one.setOrientation(LinearLayout.VERTICAL);
                one.setGravity(Gravity.CENTER_HORIZONTAL);
                one.setFocusable(true);
                FrameLayout ph = new FrameLayout(this);
                GradientDrawable circ = new GradientDrawable();
                circ.setShape(GradientDrawable.OVAL);
                circ.setColor(Ui.BG3);
                ph.setBackground(circ);
                ph.setClipToOutline(true);
                TextView ini = Ui.text(this, p.optString("name").substring(0, 1), 30, Ui.DIM, true);
                ini.setGravity(Gravity.CENTER);
                ph.addView(ini, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
                ImageView iv = new ImageView(this);
                iv.setScaleType(ImageView.ScaleType.CENTER_CROP);
                ph.addView(iv, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
                Img.load(iv, App.api.url("/api/actor?id=" + ref + "&w=200&name=" + MainActivity.enc(p.optString("name"))));
                one.addView(ph, Ui.lp(Ui.dp(this, 96), Ui.dp(this, 96)));
                TextView n = Ui.text(this, p.optString("name"), 14, Ui.FG, true);
                n.setGravity(Gravity.CENTER);
                n.setMaxWidth(Ui.dp(this, 120));
                one.addView(n);
                TextView ro = Ui.text(this, p.optString("role"), 13, Ui.DIM, false);
                ro.setGravity(Gravity.CENTER);
                ro.setMaxWidth(Ui.dp(this, 120));
                one.addView(ro);
                one.setOnFocusChangeListener((v, f) -> v.animate().scaleX(f ? 1.08f : 1f).scaleY(f ? 1.08f : 1f).setDuration(120).start());
                pr.addView(one, Ui.margins(Ui.lp(Ui.dp(this, 124), Ui.WRAP), this, 0, 0, 10, 0));
            }
            if (pr.getChildCount() > 0) {
                col.addView(Ui.text(this, "Besetzung", 21, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 28, 0, 8));
                HorizontalScrollView hs = new HorizontalScrollView(this);
                hs.setHorizontalScrollBarEnabled(false);
                hs.addView(pr);
                col.addView(hs);
            }
        }
        JSONObject media = it.optJSONObject("media");
        if (media != null) col.addView(tech(media), Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 0, 28, 0, 0));
        // Fokus wiederherstellen bzw. auf Abspielen setzen
        View want = keepTag != null ? root.findViewWithTag(keepTag) : null;
        if (want == null && play != null) want = play;
        if (want == null) want = w;
        want.requestFocus();
        first = false;
    }

    private View row(JSONArray items, boolean wide) {
        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false);
        LinearLayout r = new LinearLayout(this);
        r.setPadding(0, Ui.dp(this, 6), Ui.dp(this, 40), Ui.dp(this, 8));
        for (int i = 0; i < items.length(); i++) {
            JSONObject it = items.optJSONObject(i);
            View c = Ui.card(this, it, wide, v -> Ui.openItem(this, it.optInt("id")));
            c.setTag("c" + it.optInt("id"));
            r.addView(c);
        }
        hs.addView(r);
        return hs;
    }

    private View episodeRow(JSONObject e) {
        LinearLayout r = new LinearLayout(this);
        r.setFocusable(true);
        r.setClickable(true);
        r.setTag("e" + e.optInt("id"));
        r.setPadding(Ui.dp(this, 10), Ui.dp(this, 10), Ui.dp(this, 10), Ui.dp(this, 10));
        FrameLayout pic = new FrameLayout(this);
        pic.setBackground(Ui.round(Ui.BG3, 8, this));
        pic.setClipToOutline(true);
        ImageView iv = new ImageView(this);
        iv.setScaleType(ImageView.ScaleType.CENTER_CROP);
        pic.addView(iv, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
        Img.load(iv, App.api.url("/api/img/" + e.optInt("id") + "/thumb?w=480"));
        double pos = e.optDouble("pos", 0), dur = e.optDouble("duration", 0);
        int pw = Ui.dp(this, 260);
        if (pos > 0 && dur > 0) {
            View bar = new View(this);
            bar.setBackgroundColor(Ui.ACC);
            pic.addView(bar, new FrameLayout.LayoutParams((int) (pw * Math.min(1, pos / dur)), Ui.dp(this, 5), Gravity.BOTTOM));
        }
        r.addView(pic, Ui.lp(pw, pw * 9 / 16));
        LinearLayout tx = new LinearLayout(this);
        tx.setOrientation(LinearLayout.VERTICAL);
        tx.setPadding(Ui.dp(this, 20), 0, 0, 0);
        boolean w = e.optBoolean("watched");
        tx.addView(Ui.text(this, e.optInt("episode") + ". " + e.optString("title") + (w ? "   ✓" : ""), 19, Ui.FG, true));
        tx.addView(Ui.text(this, Ui.fmtDur(dur) + (pos > 0 && !w ? " · noch " + Ui.fmtDur(dur - pos) : ""), 15, Ui.DIM, false));
        TextView p = Ui.text(this, e.optString("plot"), 15, 0xffc8d1dc, false);
        p.setMaxLines(4);
        tx.addView(p, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 6, 0, 0));
        r.addView(tx, new LinearLayout.LayoutParams(0, Ui.WRAP, 1));
        r.setOnFocusChangeListener((v, f) -> v.setBackground(f ? Ui.roundStroke(Ui.BG2, Ui.ACC, 10, this) : null));
        r.setOnClickListener(v -> PlayerActivity.play(this, e.optInt("id"), pos > 0 && !w ? pos : 0));
        r.setOnLongClickListener(v -> {
            App.api.post("/api/watched/" + e.optInt("id"), Api.obj("watched", !w), (res, err) -> load());
            Ui.toast(this, w ? "Als ungesehen markiert" : "Als gesehen markiert");
            return true;
        });
        return r;
    }

    private View tech(JSONObject m) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.addView(Ui.text(this, "Technische Angaben", 21, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 0, 6));
        JSONObject v = m.optJSONObject("video");
        StringBuilder sb = new StringBuilder();
        if (!m.isNull("file")) sb.append("Datei: ").append(m.optString("file")).append('\n');
        if (v != null) sb.append("Video: ").append(Ui.codec(v.optString("codec"))).append(' ').append(v.optInt("width")).append('×').append(v.optInt("height")).append(v.optBoolean("hdr") ? " HDR" : "").append('\n');
        JSONArray a = m.optJSONArray("audio");
        for (int i = 0; a != null && i < a.length(); i++) {
            JSONObject x = a.optJSONObject(i);
            sb.append(i == 0 ? "Ton: " : "        ").append(Ui.lang(x.optString("lang"))).append(" · ").append(Ui.codec(x.optString("codec"))).append(' ').append(Ui.channels(x.optInt("channels"))).append('\n');
        }
        JSONArray s = m.optJSONArray("subs");
        if (s != null && s.length() > 0) {
            sb.append("Untertitel: ");
            for (int i = 0; i < s.length(); i++) sb.append(i > 0 ? ", " : "").append(Ui.lang(s.optJSONObject(i).optString("lang")));
            sb.append('\n');
        }
        l.addView(Ui.text(this, sb.toString().trim(), 15, Ui.DIM, false));
        return l;
    }
}
