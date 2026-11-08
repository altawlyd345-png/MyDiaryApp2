package org.bleremote;

import android.app.Activity;
import android.media.MediaPlayer;
import android.net.Uri;
import android.util.DisplayMetrics;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.VideoView;

import java.util.ArrayList;
import java.util.HashMap;

/** One native video player per split-screen zone. Zones are fractions of the screen; y is measured from the bottom. */
public class ZoneVideo {
    static FrameLayout root;
    static final HashMap<String, VideoView> views = new HashMap<String, VideoView>();
    static final HashMap<String, MediaPlayer> players = new HashMap<String, MediaPlayer>();
    static final HashMap<String, Float> levels = new HashMap<String, Float>();
    static final HashMap<String, Boolean> muted = new HashMap<String, Boolean>();

    static void ensureRoot(Activity a) {
        if (root == null || root.getParent() == null) {
            root = new FrameLayout(a);
            a.addContentView(root, new ViewGroup.LayoutParams(-1, -1));
        }
    }

    static void applyVolume(String id) {
        MediaPlayer mp = players.get(id);
        if (mp == null) return;
        Float lv = levels.get(id);
        Boolean m = muted.get(id);
        float f = (m != null && m.booleanValue()) ? 0f : (lv == null ? 1f : lv.floatValue());
        try { mp.setVolume(f, f); } catch (Exception e) { }
    }

    static void removeOne(String id) {
        players.remove(id); levels.remove(id); muted.remove(id);
        VideoView v = views.remove(id);
        if (v == null) return;
        try { v.stopPlayback(); } catch (Exception e) { }
        try { if (root != null) root.removeView(v); } catch (Exception e) { }
    }

    /** Stop and remove the video of one zone; other zones keep playing. */
    public static void stop(final Activity a, final String id) {
        a.runOnUiThread(new Runnable() {
            public void run() { removeOne(id); }
        });
    }

    /** Stop and remove every zone video. */
    public static void clear(final Activity a) {
        a.runOnUiThread(new Runnable() {
            public void run() {
                ArrayList<String> ids = new ArrayList<String>(views.keySet());
                for (int i = 0; i < ids.size(); i++) removeOne(ids.get(i));
                try {
                    if (root != null && root.getParent() != null) ((ViewGroup) root.getParent()).removeView(root);
                } catch (Exception e) { }
                root = null;
            }
        });
    }

    /** Pause / resume / restart / volume (arg 0..100) / mute / unmute the video of one zone. */
    public static void control(final Activity a, final String id, final String action, final int arg) {
        a.runOnUiThread(new Runnable() {
            public void run() {
                try {
                    VideoView v = views.get(id);
                    if (v == null) return;
                    if (action.equals("pause")) v.pause();
                    else if (action.equals("resume")) v.start();
                    else if (action.equals("restart")) { v.seekTo(0); v.start(); }
                    else if (action.equals("volume")) { levels.put(id, Float.valueOf(Math.max(0, Math.min(100, arg)) / 100f)); muted.put(id, Boolean.FALSE); applyVolume(id); }
                    else if (action.equals("mute")) { muted.put(id, Boolean.TRUE); applyVolume(id); }
                    else if (action.equals("unmute")) { muted.put(id, Boolean.FALSE); applyVolume(id); }
                } catch (Exception e) { }
            }
        });
    }

    /** Play a video (file path, or a content:// uri when uri is not empty) inside the zone rectangle x,y,w,h. volume = 0..1. */
    public static void play(final Activity a, final String id, final String path, final String uri,
                            final float x, final float y, final float w, final float h,
                            final boolean loop, final boolean mute, final float volume) {
        a.runOnUiThread(new Runnable() {
            public void run() {
                try {
                    removeOne(id);
                    ensureRoot(a);
                    DisplayMetrics dm = a.getResources().getDisplayMetrics();
                    int pw = root.getWidth() > 0 ? root.getWidth() : dm.widthPixels;
                    int ph = root.getHeight() > 0 ? root.getHeight() : dm.heightPixels;
                    FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                            Math.max(1, Math.round(w * pw)), Math.max(1, Math.round(h * ph)));
                    lp.leftMargin = Math.round(x * pw);
                    lp.topMargin = Math.round((1f - y - h) * ph);
                    final VideoView v = new VideoView(a);
                    v.setZOrderMediaOverlay(true);
                    root.addView(v, lp);
                    views.put(id, v);
                    levels.put(id, Float.valueOf(volume));
                    muted.put(id, Boolean.valueOf(mute));
                    if (uri != null && uri.length() > 0) v.setVideoURI(Uri.parse(uri));
                    else v.setVideoPath(path);
                    v.setOnPreparedListener(new MediaPlayer.OnPreparedListener() {
                        public void onPrepared(MediaPlayer mp) {
                            mp.setLooping(loop);
                            players.put(id, mp);
                            applyVolume(id);
                            v.start();
                        }
                    });
                } catch (Exception e) { }
            }
        });
    }
}
