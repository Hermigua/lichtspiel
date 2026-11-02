package de.lichtspiel.tv;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** Server-Adresse eingeben, Profil wählen, ggf. Passwort – danach Hauptbildschirm. */
public class SetupActivity extends Activity {
    private LinearLayout box;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = new LinearLayout(this);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(Ui.BG);
        box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(box, Ui.lp(Ui.dp(this, 760), Ui.WRAP));
        setContentView(root);
        serverStep(null);
    }

    private void header(String sub) {
        box.removeAllViews();
        LinearLayout brand = new LinearLayout(this);
        brand.setGravity(Gravity.CENTER);
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo);
        brand.addView(logo, Ui.lp(Ui.dp(this, 64), Ui.dp(this, 64)));
        TextView n = Ui.text(this, "Lichtspiel", 34, Ui.FG, true);
        n.setPadding(Ui.dp(this, 14), 0, 0, 0);
        brand.addView(n);
        box.addView(brand);
        TextView s = Ui.text(this, sub, 20, Ui.DIM, false);
        s.setGravity(Gravity.CENTER);
        box.addView(s, Ui.margins(Ui.lp(Ui.MATCH, Ui.WRAP), this, 0, 18, 0, 18));
    }

    private EditText input(String value, String hint, boolean pw) {
        EditText e = new EditText(this);
        e.setText(value);
        e.setHint(hint);
        e.setHintTextColor(Ui.DIM);
        e.setTextColor(Ui.FG);
        e.setSingleLine(true);
        e.setTextSize(20);
        if (pw) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        else e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        e.setImeOptions(EditorInfo.IME_ACTION_DONE);
        e.setBackground(Ui.roundStroke(Ui.BG3, Ui.LINE, 10, this));
        e.setOnFocusChangeListener((v, f) -> v.setBackground(Ui.roundStroke(Ui.BG3, f ? Ui.ACC : Ui.LINE, 10, this)));
        e.setPadding(Ui.dp(this, 16), Ui.dp(this, 12), Ui.dp(this, 16), Ui.dp(this, 12));
        return e;
    }

    private void serverStep(String err) {
        header("Adresse des Lichtspiel-Servers");
        String cur = App.api.server().isEmpty() ? BuildConfig.DEFAULT_SERVER : App.api.server();
        EditText in = input(cur, "http://192.168.1.10:8400", false);
        box.addView(in, Ui.lp(Ui.MATCH, Ui.WRAP));
        TextView msg = Ui.text(this, err == null ? "" : err, 16, 0xfffca5a5, false);
        box.addView(msg, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 10, 0, 0));
        Runnable go = () -> {
            String s = in.getText().toString().trim();
            if (!s.startsWith("http")) s = "http://" + s;
            App.api.setServer(s);
            msg.setText("Verbinde …");
            App.api.get("/api/state", (r, e) -> {
                if (e != null) { serverStep("Keine Verbindung: " + e); return; }
                if (Api.o(r).optBoolean("setup")) { serverStep("Der Server ist noch nicht eingerichtet – bitte zuerst im Browser öffnen."); return; }
                profiles();
            });
        };
        TextView ok = Ui.button(this, "Weiter", v -> go.run());
        box.addView(ok, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 16, 0, 0));
        in.setOnEditorActionListener((v, a, ev) -> { ok.requestFocus(); return false; });
        in.requestFocus();
    }

    private void profiles() {
        App.api.get("/api/profiles", (r, e) -> {
            header("Wer schaut?");
            JSONArray p = Api.arr(r);
            LinearLayout row = new LinearLayout(this);
            row.setGravity(Gravity.CENTER);
            for (int i = 0; i < p.length(); i++) {
                JSONObject u = p.optJSONObject(i);
                LinearLayout one = new LinearLayout(this);
                one.setOrientation(LinearLayout.VERTICAL);
                one.setGravity(Gravity.CENTER_HORIZONTAL);
                one.setFocusable(true);
                one.setClickable(true);
                one.setPadding(Ui.dp(this, 10), Ui.dp(this, 10), Ui.dp(this, 10), Ui.dp(this, 10));
                TextView av = Ui.text(this, u.optString("name").substring(0, 1).toUpperCase(), 44, 0xff0d1117, true);
                av.setGravity(Gravity.CENTER);
                int col = Color.parseColor(u.optString("color", "#2ec4b6"));
                av.setBackground(Ui.round(col, 18, this));
                one.addView(av, Ui.lp(Ui.dp(this, 110), Ui.dp(this, 110)));
                TextView nm = Ui.text(this, u.optString("name"), 18, Ui.FG, false);
                nm.setGravity(Gravity.CENTER);
                nm.setMaxWidth(Ui.dp(this, 130));
                one.addView(nm, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 8, 0, 0));
                one.setOnFocusChangeListener((v, f) -> {
                    v.animate().scaleX(f ? 1.1f : 1f).scaleY(f ? 1.1f : 1f).setDuration(120).start();
                    av.setBackground(f ? Ui.roundStroke(col, Ui.FG, 18, this) : Ui.round(col, 18, this));
                });
                one.setOnClickListener(v -> {
                    if (u.optBoolean("has_pw")) password(u.optString("name"), null);
                    else login(u.optString("name"), "");
                });
                row.addView(one, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 12, 0, 12, 0));
            }
            box.addView(row);
            box.addView(Ui.button(this, "Server ändern", v -> serverStep(null)), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 30, 0, 0));
            if (row.getChildCount() > 0) row.getChildAt(0).requestFocus();
        });
    }

    private void password(String name, String err) {
        header("Passwort für " + name);
        EditText in = input("", "Passwort", true);
        box.addView(in, Ui.lp(Ui.MATCH, Ui.WRAP));
        if (err != null) box.addView(Ui.text(this, err, 16, 0xfffca5a5, false), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 10, 0, 0));
        TextView ok = Ui.button(this, "Anmelden", v -> login(name, in.getText().toString()));
        box.addView(ok, Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 16, 0, 0));
        box.addView(Ui.button(this, "Anderes Profil", v -> profiles()), Ui.margins(Ui.lp(Ui.WRAP, Ui.WRAP), this, 0, 10, 0, 0));
        in.setOnEditorActionListener((v, a, ev) -> { login(name, in.getText().toString()); return true; });
        in.requestFocus();
    }

    private void login(String name, String pw) {
        App.api.post("/api/login", Api.obj("name", name, "password", pw), (r, e) -> {
            if (e != null) { password(name, e.replaceFirst("^401:", "")); return; }
            App.api.setToken(Api.o(r).optString("token"));
            startActivity(new Intent(this, MainActivity.class));
            finish();
        });
    }
}
