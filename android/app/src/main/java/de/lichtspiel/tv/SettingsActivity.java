package de.lichtspiel.tv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

/** Einstellungen: Wiedergabe und Untertitel (gelten fürs Profil), Darstellung (nur dieses Gerät), Konto. */
public class SettingsActivity extends Activity {
    private LinearLayout col;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Ui.BG);
        col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(Ui.dp(this, 80), Ui.dp(this, 36), Ui.dp(this, 80), Ui.dp(this, 40));
        sv.addView(col);
        setContentView(sv);
        App.api.get("/api/me/prefs", (r, e) -> {
            if (r instanceof JSONObject) App.api.prefs = (JSONObject) r;
            render();
        });
    }

    private void head(String t) {
        col.addView(Ui.text(this, t, 22, Ui.FG, true), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 22, 0, 8));
    }

    /** Zeile, die beim Drücken von OK zur nächsten Option weiterschaltet. */
    private void choice(String label, String key, Object[] vals, String[] names, boolean local) {
        TextView t = Ui.button(this, "", null);
        t.setGravity(android.view.Gravity.START);
        Runnable draw = () -> {
            Object cur = local ? App.api.local().getFloat(key, 1f) : App.api.prefs.opt(key);
            int i = idx(vals, cur);
            t.setText(label + ":   " + (i >= 0 ? names[i] : String.valueOf(cur)));
        };
        draw.run();
        t.setOnClickListener(v -> {
            Object cur = local ? App.api.local().getFloat(key, 1f) : App.api.prefs.opt(key);
            Object nv = vals[(idx(vals, cur) + 1) % vals.length];
            if (local) {
                App.api.local().edit().putFloat(key, (Float) nv).apply();
                Ui.scale = (Float) nv;
            } else {
                try { App.api.prefs.put(key, nv); } catch (Exception ignored) { }
                App.api.put("/api/me/prefs", Api.obj(key, nv), null);
            }
            draw.run();
        });
        col.addView(t, Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 0, 4, 0, 4));
    }

    private static int idx(Object[] vals, Object cur) {
        for (int i = 0; i < vals.length; i++) {
            if (vals[i].equals(cur)) return i;
            if (vals[i] instanceof Number && cur instanceof Number && ((Number) vals[i]).doubleValue() == ((Number) cur).doubleValue()) return i;
        }
        return -1;
    }

    private void render() {
        col.removeAllViews();
        col.addView(Ui.text(this, "Einstellungen", 30, Ui.FG, true));
        head("Wiedergabe");
        choice("Qualität", "quality", new Object[]{0, 1080, 720, 480}, new String[]{"Original", "1080p", "720p", "480p"}, false);
        choice("Direktwiedergabe", "direct", new Object[]{true, false}, new String[]{"Erlaubt", "Immer umwandeln"}, false);
        choice("Bevorzugte Tonspur", "audio_lang", new Object[]{"deu", "eng", "fra", "spa", "ita"}, new String[]{"Deutsch", "Englisch", "Französisch", "Spanisch", "Italienisch"}, false);
        choice("Nächste Folge automatisch", "autoplay", new Object[]{true, false}, new String[]{"Ja", "Nein"}, false);
        choice("Zurückspringen", "skip_back", new Object[]{5, 10, 15, 30}, new String[]{"5 s", "10 s", "15 s", "30 s"}, false);
        choice("Vorspringen", "skip_fwd", new Object[]{10, 15, 30, 60}, new String[]{"10 s", "15 s", "30 s", "60 s"}, false);
        head("Untertitel");
        choice("Automatisch einschalten", "sub_mode", new Object[]{"off", "forced", "foreign", "always"}, new String[]{"Nie", "Nur erzwungene", "Bei fremder Tonspur", "Immer"}, false);
        choice("Sprache", "sub_lang", new Object[]{"deu", "eng", "fra", "spa", "ita"}, new String[]{"Deutsch", "Englisch", "Französisch", "Spanisch", "Italienisch"}, false);
        choice("Größe", "sub_size", new Object[]{75, 100, 125, 150}, new String[]{"Klein", "Normal", "Groß", "Sehr groß"}, false);
        choice("Hintergrund", "sub_bg", new Object[]{0, 1}, new String[]{"Ohne (Schatten)", "Dunkler Kasten"}, false);
        head("Darstellung (dieses Gerät)");
        choice("Größe", "scale", new Object[]{0.8f, 0.9f, 1f, 1.15f}, new String[]{"Klein", "Mittel", "Normal", "Groß"}, true);
        head("Konto");
        String u = App.api.user != null ? App.api.user.optString("name") : "";
        col.addView(Ui.text(this, "Angemeldet als " + u + " auf " + App.api.server(), 16, Ui.DIM, false));
        col.addView(Ui.button(this, "Profil wechseln", v -> {
            App.api.post("/api/logout", null, (r, e) -> {
                App.api.setToken("");
                startActivity(new Intent(this, SetupActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
            });
        }), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 8, 0, 0));
        head("Info");
        col.addView(Ui.text(this, "Lichtspiel TV " + BuildConfig.VERSION_NAME + " – eigener Code ohne fremde Bibliotheken, gemeinfrei (The Unlicense).", 16, Ui.DIM, false));
        col.getChildAt(2).requestFocus();
    }

    @Override protected void onPause() {
        super.onPause();
        // Darstellungsgröße wirkt nach Neustart des Hauptbildschirms
    }

    @Override public void onBackPressed() {
        startActivity(new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }
}
