package de.lichtspiel.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.AbsListView;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridView;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** Hauptbildschirm: Seitenmenü links, Inhalt rechts (Start, Bibliotheken, Live-TV, Sender, Suche). */
public class MainActivity extends Activity {
    private LinearLayout menu;
    private FrameLayout content;
    private String screen = "home";
    private int libId;
    private final List<TextView> menuItems = new ArrayList<>();
    private JSONArray libs = new JSONArray();
    private long backAt;
    private int seq;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        Ui.scale = App.api.local().getFloat("scale", 1f);
        LinearLayout root = new LinearLayout(this);
        root.setBackgroundColor(Ui.BG);
        menu = new LinearLayout(this);
        menu.setOrientation(LinearLayout.VERTICAL);
        menu.setBackgroundColor(Ui.BG2);
        menu.setPadding(Ui.dp(this, 14), Ui.dp(this, 20), Ui.dp(this, 14), Ui.dp(this, 20));
        ScrollView ms = new ScrollView(this);
        ms.addView(menu);
        root.addView(ms, Ui.lp(Ui.dp(this, 230), Ui.MATCH));
        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(0, Ui.MATCH, 1));
        setContentView(root);
        if (App.api.server().isEmpty() || App.api.token().isEmpty()) { startSetup(); return; }
        boot();
    }

    private void startSetup() {
        startActivity(new Intent(this, SetupActivity.class));
        finish();
    }

    private void boot() {
        App.api.get("/api/state", (r, e) -> {
            if (e != null) { message("Server nicht erreichbar:\n" + e + "\n\n" + App.api.server(), true); return; }
            JSONObject st = Api.o(r);
            if (st.isNull("user")) { startSetup(); return; }
            App.api.user = st.optJSONObject("user");
            App.api.prefs = st.optJSONObject("prefs") != null ? st.optJSONObject("prefs") : new JSONObject();
            App.api.get("/api/libraries", (l, e2) -> {
                libs = Api.arr(l);
                buildMenu();
                show(screen);
            });
        });
    }

    private void buildMenu() {
        menu.removeAllViews();
        menuItems.clear();
        LinearLayout brand = new LinearLayout(this);
        brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo);
        brand.addView(logo, Ui.lp(Ui.dp(this, 40), Ui.dp(this, 40)));
        TextView name = Ui.text(this, "Lichtspiel", 21, Ui.FG, true);
        name.setPadding(Ui.dp(this, 10), 0, 0, 0);
        brand.addView(name);
        menu.addView(brand, Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 4, 0, 0, 18));
        addMenu("Start", "home");
        addMenu("Suche", "search");
        for (int i = 0; i < libs.length(); i++) {
            JSONObject l = libs.optJSONObject(i);
            if (l.optBoolean("hidden")) continue;
            addMenu(l.optString("name"), "lib:" + l.optInt("id"));
        }
        addMenu("Live-TV", "live");
        addMenu("Sender", "channels");
        addMenu("Einstellungen", "settings");
    }

    private void addMenu(String label, String key) {
        TextView t = Ui.text(this, label, 18, Ui.DIM, false);
        t.setFocusable(true);
        t.setClickable(true);
        t.setPadding(Ui.dp(this, 14), Ui.dp(this, 10), Ui.dp(this, 14), Ui.dp(this, 10));
        t.setTag(key);
        t.setOnFocusChangeListener((v, f) -> styleMenu());
        t.setOnClickListener(v -> {
            if (key.equals("settings")) { startActivity(new Intent(this, SettingsActivity.class)); return; }
            show(key);
            focusContent();
        });
        menu.addView(t, Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 0, 2, 0, 2));
        menuItems.add(t);
    }

    private void styleMenu() {
        for (TextView t : menuItems) {
            boolean cur = t.getTag().equals(screen) || (screen.startsWith("lib:") && t.getTag().equals(screen));
            boolean f = t.hasFocus();
            t.setBackground(f ? Ui.round(Ui.ACC, 8, this) : cur ? Ui.round(Ui.BG3, 8, this) : null);
            t.setTextColor(f ? 0xff04201e : cur ? Ui.FG : Ui.DIM);
        }
    }

    private void focusContent() {
        content.postDelayed(() -> {
            View v = content.getChildCount() > 0 ? content.getChildAt(0) : null;
            if (v != null) v.requestFocus(View.FOCUS_RIGHT);
        }, 300);
    }

    @Override protected void onResume() {
        super.onResume();
        if (App.api.user != null && (screen.equals("home") || screen.startsWith("lib:"))) {
            if (screen.equals("home")) show("home");
        }
    }

    @Override public boolean onKeyDown(int code, KeyEvent ev) {
        if (code == KeyEvent.KEYCODE_BACK) {
            View f = getCurrentFocus();
            boolean inMenu = f != null && menuItems.contains(f);
            if (!inMenu && !menuItems.isEmpty()) {
                for (TextView t : menuItems) if (t.getTag().equals(screen)) { t.requestFocus(); return true; }
                menuItems.get(0).requestFocus();
                return true;
            }
            if (System.currentTimeMillis() - backAt < 2500) { finish(); return true; }
            backAt = System.currentTimeMillis();
            Ui.toast(this, "Nochmal Zurück zum Beenden");
            return true;
        }
        return super.onKeyDown(code, ev);
    }

    private void message(String s, boolean retry) {
        content.removeAllViews();
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setGravity(Gravity.CENTER);
        l.addView(Ui.text(this, s, 18, Ui.FG, false));
        if (retry) {
            l.addView(Ui.button(this, "Erneut versuchen", v -> boot()), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 20, 0, 0));
            l.addView(Ui.button(this, "Server ändern", v -> startSetup()), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 10, 0, 0));
        }
        content.addView(l, new FrameLayout.LayoutParams(Ui.MATCH, Ui.MATCH));
        if (retry) l.getChildAt(1).requestFocus();
    }

    private void show(String key) {
        screen = key;
        styleMenu();
        int my = ++seq;
        if (key.equals("home")) home(my);
        else if (key.startsWith("lib:")) library(Integer.parseInt(key.substring(4)), my);
        else if (key.equals("live")) live(my);
        else if (key.equals("channels")) channels(my);
        else if (key.equals("search")) search();
    }

    // ---------------- Start ----------------
    private void home(int my) {
        App.api.get("/api/home", (r, e) -> {
            if (my != seq) return;
            if (e != null) { if (e.startsWith("401")) startSetup(); else message(e, true); return; }
            boolean hadFocus = content.hasFocus();
            ScrollView sv = new ScrollView(this);
            LinearLayout col = new LinearLayout(this);
            col.setOrientation(LinearLayout.VERTICAL);
            col.setPadding(Ui.dp(this, 24), Ui.dp(this, 18), Ui.dp(this, 24), Ui.dp(this, 40));
            JSONArray hubs = Api.o(r).optJSONArray("hubs");
            if (hubs == null || hubs.length() == 0) col.addView(Ui.text(this, "Noch nichts zu sehen – Bibliotheken im Browser anlegen.", 18, Ui.DIM, false));
            for (int i = 0; hubs != null && i < hubs.length(); i++) {
                JSONObject h = hubs.optJSONObject(i);
                col.addView(Ui.text(this, h.optString("title"), 20, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 6, 10, 0, 4));
                col.addView(row(h.optJSONArray("items"), h.optBoolean("wide")));
            }
            sv.addView(col);
            content.removeAllViews();
            content.addView(sv);
            if (hadFocus) focusContent();
        });
    }

    private View row(JSONArray items, boolean wide) {
        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false);
        hs.setClipToPadding(false);
        LinearLayout r = new LinearLayout(this);
        r.setPadding(0, Ui.dp(this, 6), Ui.dp(this, 40), Ui.dp(this, 8));
        r.setClipChildren(false);
        for (int i = 0; items != null && i < items.length(); i++) {
            JSONObject it = items.optJSONObject(i);
            r.addView(Ui.card(this, it, wide, v -> Ui.openItem(this, it.optInt("id"))));
        }
        hs.addView(r);
        return hs;
    }

    // ---------------- Bibliothek ----------------
    private static final String[][] SORTS = {{"title", "Titel"}, {"added", "Zuletzt hinzugefügt"}, {"year", "Jahr"}, {"rating", "Bewertung"}};
    private int sortIdx = 0;
    private boolean unwatched = false;
    private String genre = "";

    private void library(int id, int my) {
        libId = id;
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(Ui.dp(this, 20), Ui.dp(this, 16), Ui.dp(this, 20), 0);
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        String libName = "";
        for (int i = 0; i < libs.length(); i++) if (libs.optJSONObject(i).optInt("id") == id) libName = libs.optJSONObject(i).optString("name");
        bar.addView(Ui.text(this, libName, 24, Ui.FG, true));
        TextView cnt = Ui.text(this, "", 16, Ui.DIM, false);
        cnt.setPadding(Ui.dp(this, 14), 0, Ui.dp(this, 20), 0);
        bar.addView(cnt, new LinearLayout.LayoutParams(0, Ui.WRAP, 1));
        GridView grid = new GridView(this);
        LibAdapter ad = new LibAdapter();
        TextView bSort = Ui.button(this, "Sortierung: " + SORTS[sortIdx][1], null);
        bSort.setOnClickListener(v -> { sortIdx = (sortIdx + 1) % SORTS.length; bSort.setText("Sortierung: " + SORTS[sortIdx][1]); ad.reload(id, cnt); });
        TextView bUnw = Ui.button(this, unwatched ? "Nur ungesehene" : "Alle", null);
        bUnw.setOnClickListener(v -> { unwatched = !unwatched; bUnw.setText(unwatched ? "Nur ungesehene" : "Alle"); ad.reload(id, cnt); });
        TextView bGen = Ui.button(this, genre.isEmpty() ? "Alle Genres" : genre, null);
        bGen.setOnClickListener(v -> App.api.get("/api/lib/" + id + "/genres", (r, e) -> {
            JSONArray g = Api.arr(r);
            String[] names = new String[g.length() + 1];
            names[0] = "Alle Genres";
            for (int i = 0; i < g.length(); i++) names[i + 1] = g.optJSONObject(i).optString("g");
            new AlertDialog.Builder(this).setItems(names, (d, w) -> {
                genre = w == 0 ? "" : names[w];
                bGen.setText(names[w]);
                ad.reload(id, cnt);
            }).show();
        }));
        bar.addView(bSort, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 10, 0));
        bar.addView(bGen, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 10, 0));
        bar.addView(bUnw);
        col.addView(bar, Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 0, 0, 0, 10));
        grid.setColumnWidth(Ui.dp(this, 172));
        grid.setNumColumns(GridView.AUTO_FIT);
        grid.setStretchMode(GridView.STRETCH_SPACING);
        grid.setVerticalSpacing(Ui.dp(this, 10));
        grid.setSelector(new android.graphics.drawable.ColorDrawable(0));
        grid.setClipToPadding(false);
        grid.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 40));
        grid.setAdapter(ad);
        grid.setOnItemClickListener((p, v, pos, rid) -> Ui.openItem(this, ad.items.get(pos).optInt("id")));
        final View[] last = {null};
        grid.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> p, View v, int pos, long rid) {
                Ui.hi(last[0], false); Ui.hi(v, true); last[0] = v;
            }
            @Override public void onNothingSelected(AdapterView<?> p) { Ui.hi(last[0], false); last[0] = null; }
        });
        grid.setOnFocusChangeListener((v, f) -> { if (!f) { Ui.hi(last[0], false); } else if (grid.getSelectedView() != null) { last[0] = grid.getSelectedView(); Ui.hi(last[0], true); } });
        grid.setOnScrollListener(new AbsListView.OnScrollListener() {
            @Override public void onScrollStateChanged(AbsListView v, int s) { }
            @Override public void onScroll(AbsListView v, int first, int visible, int total) {
                if (total > 0 && first + visible >= total - 20) ad.more(id, cnt);
            }
        });
        col.addView(grid, new LinearLayout.LayoutParams(Ui.MATCH, 0, 1));
        content.removeAllViews();
        content.addView(col);
        ad.reload(id, cnt);
    }

    private class LibAdapter extends BaseAdapter {
        final List<JSONObject> items = new ArrayList<>();
        int total = 0, gen = 0;
        boolean busy = false;
        boolean shows = false;

        void reload(int id, TextView cnt) { items.clear(); total = 0; gen++; busy = false; notifyDataSetChanged(); more(id, cnt); }

        void more(int id, TextView cnt) {
            if (busy || (total > 0 && items.size() >= total)) return;
            busy = true;
            int g = gen;
            String q = "/api/lib/" + id + "/items?limit=150&offset=" + items.size() + "&sort=" + SORTS[sortIdx][0] +
                    (unwatched ? "&unwatched=1" : "") + (genre.isEmpty() ? "" : "&genre=" + enc(genre));
            App.api.get(q, (r, e) -> {
                if (g != gen) return;
                busy = false;
                if (e != null) { Ui.toast(MainActivity.this, e); return; }
                JSONObject j = Api.o(r);
                total = j.optInt("total");
                shows = "show".equals(j.optString("kind"));
                JSONArray a = j.optJSONArray("items");
                for (int i = 0; a != null && i < a.length(); i++) items.add(a.optJSONObject(i));
                if (a == null || a.length() == 0) total = items.size();
                cnt.setText(total + (shows ? " Serien" : " Filme"));
                notifyDataSetChanged();
            });
        }
        @Override public int getCount() { return items.size(); }
        @Override public Object getItem(int p) { return items.get(p); }
        @Override public long getItemId(int p) { return items.get(p).optInt("id"); }
        @Override public View getView(int p, View cv, ViewGroup parent) {
            View v = Ui.card(MainActivity.this, items.get(p), false, null);
            v.setFocusable(false);
            v.setClickable(false);
            return v;
        }
    }

    static String enc(String s) {
        try { return URLEncoder.encode(s, "UTF-8"); } catch (Exception e) { return s; }
    }

    // ---------------- Live-TV / Sender ----------------
    private static final SimpleDateFormat HM = new SimpleDateFormat("HH:mm", Locale.GERMANY);
    static String hm(double t) { return HM.format(new Date((long) (t * 1000))); }

    private void tiles(String title, JSONArray list, String logoBase, String emptyMsg, TileClick click) {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(Ui.dp(this, 20), Ui.dp(this, 16), Ui.dp(this, 20), 0);
        col.addView(Ui.text(this, title, 24, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 0, 0, 10));
        if (list.length() == 0) col.addView(Ui.text(this, emptyMsg, 18, Ui.DIM, false));
        GridView grid = new GridView(this);
        grid.setColumnWidth(Ui.dp(this, 312));
        grid.setNumColumns(GridView.AUTO_FIT);
        grid.setStretchMode(GridView.STRETCH_SPACING);
        grid.setVerticalSpacing(Ui.dp(this, 10));
        grid.setSelector(new android.graphics.drawable.ColorDrawable(0));
        grid.setClipToPadding(false);
        grid.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 40));
        List<JSONObject> items = new ArrayList<>();
        for (int i = 0; i < list.length(); i++) {
            JSONObject c = list.optJSONObject(i);
            JSONObject now = c.optJSONObject("now"), nxt = c.optJSONObject("next");
            JSONObject card = Api.obj("id", c.optInt("id"), "kind", "channel", "title", c.optString("name"),
                    "img", logoBase + c.optInt("id") + "/logo");
            try {
                if (c.optInt("number") > 0) card.put("badge", String.valueOf(c.optInt("number")));
                String sub = now != null ? hm(now.optDouble("start")) + " " + now.optString("title") : "Kein Programm";
                if (nxt != null) sub += "\n" + hm(nxt.optDouble("start")) + " " + nxt.optString("title");
                card.put("sub", sub);
            } catch (Exception ignored) { }
            items.add(card);
        }
        grid.setAdapter(new BaseAdapter() {
            @Override public int getCount() { return items.size(); }
            @Override public Object getItem(int p) { return items.get(p); }
            @Override public long getItemId(int p) { return p; }
            @Override public View getView(int p, View cv, ViewGroup parent) {
                JSONObject it = items.get(p);
                View v = Ui.card(MainActivity.this, it, true, null);
                ImageView iv = (ImageView) ((ViewGroup) ((ViewGroup) v).getChildAt(0)).getChildAt(1);
                iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
                iv.setPadding(Ui.dp(MainActivity.this, 50), Ui.dp(MainActivity.this, 30), Ui.dp(MainActivity.this, 50), Ui.dp(MainActivity.this, 30));
                TextView s = Ui.text(MainActivity.this, it.optString("sub"), 13, Ui.DIM, false);
                ((ViewGroup) v).addView(s);
                v.setFocusable(false);
                v.setClickable(false);
                return v;
            }
        });
        final View[] last = {null};
        grid.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> p, View v, int pos, long rid) { Ui.hi(last[0], false); Ui.hi(v, true); last[0] = v; }
            @Override public void onNothingSelected(AdapterView<?> p) { Ui.hi(last[0], false); last[0] = null; }
        });
        grid.setOnFocusChangeListener((v, f) -> { if (!f) Ui.hi(last[0], false); else if (grid.getSelectedView() != null) { last[0] = grid.getSelectedView(); Ui.hi(last[0], true); } });
        grid.setOnItemClickListener((p, v, pos, rid) -> click.on(pos, items));
        col.addView(grid, new LinearLayout.LayoutParams(Ui.MATCH, 0, 1));
        content.removeAllViews();
        content.addView(col);
    }

    interface TileClick { void on(int pos, List<JSONObject> items); }

    private void live(int my) {
        App.api.get("/api/live", (r, e) -> {
            if (my != seq) return;
            JSONArray l = Api.arr(r);
            tiles("Live-TV", l, "/api/live/", "Keine Sender – Senderlisten im Browser unter Einstellungen → Live-TV eintragen.", (pos, items) -> {
                int[] ids = new int[items.size()];
                String[] names = new String[items.size()];
                for (int i = 0; i < ids.length; i++) { ids[i] = items.get(i).optInt("id"); names[i] = items.get(i).optString("title"); }
                startActivity(new Intent(this, PlayerActivity.class).putExtra("live", ids[pos]).putExtra("live_ids", ids).putExtra("live_names", names));
            });
        });
    }

    private void channels(int my) {
        App.api.get("/api/channels", (r, e) -> {
            if (my != seq) return;
            JSONArray all = Api.arr(r), l = new JSONArray();
            for (int i = 0; i < all.length(); i++) if (all.optJSONObject(i).optBoolean("enabled") && all.optJSONObject(i).optInt("count") > 0) l.put(all.optJSONObject(i));
            tiles("Sender", l, "/api/channels/", "Noch keine eigenen Sender – im Browser unter Einstellungen → Eigene Sender anlegen.", (pos, items) ->
                    PlayerActivity.tune(this, items.get(pos).optInt("id"), items.get(pos).optString("title")));
        });
    }

    // ---------------- Suche ----------------
    private void search() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(Ui.dp(this, 24), Ui.dp(this, 18), Ui.dp(this, 24), 0);
        EditText in = new EditText(this);
        in.setHint("Titel oder Person suchen …");
        in.setHintTextColor(Ui.DIM);
        in.setTextColor(Ui.FG);
        in.setSingleLine(true);
        in.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        in.setBackground(Ui.round(Ui.BG3, 10, this));
        in.setPadding(Ui.dp(this, 16), Ui.dp(this, 10), Ui.dp(this, 16), Ui.dp(this, 10));
        col.addView(in, Ui.lp(Ui.MATCH, Ui.WRAP));
        ScrollView sv = new ScrollView(this);
        LinearLayout res = new LinearLayout(this);
        res.setOrientation(LinearLayout.VERTICAL);
        sv.addView(res);
        col.addView(sv, new LinearLayout.LayoutParams(Ui.MATCH, 0, 1));
        final int[] gen = {0};
        Runnable run = () -> {
            String q = in.getText().toString().trim();
            if (q.length() < 2) return;
            int g = ++gen[0];
            App.api.get("/api/search?q=" + enc(q), (r, e) -> {
                if (g != gen[0]) return;
                res.removeAllViews();
                JSONObject j = Api.o(r);
                JSONArray items = j.optJSONArray("items"), mv = new JSONArray(), ep = new JSONArray();
                for (int i = 0; items != null && i < items.length(); i++) (items.optJSONObject(i).optString("kind").equals("episode") ? ep : mv).put(items.optJSONObject(i));
                if (mv.length() > 0) { res.addView(Ui.text(this, "Filme & Serien", 20, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 6, 14, 0, 4)); res.addView(row(mv, false)); }
                if (ep.length() > 0) { res.addView(Ui.text(this, "Folgen", 20, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 6, 14, 0, 4)); res.addView(row(ep, true)); }
                JSONArray ppl = j.optJSONArray("people");
                if (ppl != null && ppl.length() > 0) { res.addView(Ui.text(this, "Mit „" + q + "“", 20, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 6, 14, 0, 4)); res.addView(row(ppl, false)); }
                if (res.getChildCount() == 0) res.addView(Ui.text(this, "Nichts gefunden.", 18, Ui.DIM, false));
            });
        };
        in.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { in.removeCallbacks(run); in.postDelayed(run, 500); }
            @Override public void afterTextChanged(Editable s) { }
        });
        in.setOnEditorActionListener((v, a, ev) -> { run.run(); res.postDelayed(() -> res.requestFocus(View.FOCUS_DOWN), 600); return false; });
        content.removeAllViews();
        content.addView(col);
    }
}
