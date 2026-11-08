package org.bleremote;

import android.app.Activity;
import android.os.Build;
import android.view.View;
import android.view.WindowManager;

/** Immersive sticky UI helper for WALIBRA Receiver kiosk presentation. */
public final class KioskHelper {
    private KioskHelper() {}
    public static void setImmersive(Activity activity, boolean enabled) {
        if (activity == null) return;
        if (enabled) {
            activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            final View decor = activity.getWindow().getDecorView();
            int flags = View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION;
            decor.setSystemUiVisibility(flags);
        } else {
            activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            activity.getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
        }
    }
}
