package de.lichtspiel.tv;

import android.app.Application;

public class App extends Application {
    public static Api api;

    @Override public void onCreate() {
        super.onCreate();
        api = new Api(this);
        Img.init(this);
        if (api.server().isEmpty() && !BuildConfig.DEFAULT_SERVER.equals("http://")) api.setServer(BuildConfig.DEFAULT_SERVER);
    }
}
