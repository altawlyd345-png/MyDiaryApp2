package org.bleremote;

import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedDeque;

/**
 * Receiver BLE server (hardened).
 * - ensureRunning() can be called repeatedly (Python watchdog): it (re)creates the GATT server and
 *   (re)starts advertising whenever Bluetooth was off at launch, was toggled, or advertising stopped.
 * - Notifications are sent one at a time (waits for onNotificationSent) so ACK fragments are not dropped.
 * - No exception can escape to a Binder thread.
 */
public class BleServer {
    static final UUID SVC = UUID.fromString("12345678-1234-5678-1234-56789abcdef0");
    static final UUID W = UUID.fromString("12345678-1234-5678-1234-56789abcdef1");
    static final UUID N = UUID.fromString("12345678-1234-5678-1234-56789abcdef2");
    static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    Context ctx; BluetoothManager mgr; BluetoothGattServer server; BluetoothDevice dev;
    BluetoothGattCharacteristic nc;
    volatile String state = "idle"; volatile int mtu = 23;
    volatile boolean serviceReady = false, advertising = false, notifying = false, notificationsEnabled = false;
    long notifyT = 0; int waits = 0; byte[] inFlight = null;
    final Handler main = new Handler(Looper.getMainLooper());
    final ConcurrentLinkedDeque<byte[]> in = new ConcurrentLinkedDeque<>();
    final ConcurrentLinkedDeque<byte[]> outq = new ConcurrentLinkedDeque<>();

    public BleServer(Context c) {
        ctx = c;
        mgr = (BluetoothManager) c.getSystemService(Context.BLUETOOTH_SERVICE);
    }

    /** Safe to call every few seconds. */
    public synchronized void ensureRunning() {
        try {
            BluetoothAdapter ad = mgr.getAdapter();
            if (ad == null || !ad.isEnabled()) {
                state = "bt_off";
                if (server != null) { try { server.close(); } catch (Exception e) { } }
                server = null; serviceReady = false; advertising = false; dev = null; notifying = false; outq.clear();
                return;
            }
            if (server == null) { waits = 0; start(); return; }
            if (!serviceReady) { if (++waits > 3) { waits = 0; start(); } return; }
            waits = 0;
            if (dev == null) advertise();     // harmless if already advertising (ALREADY_STARTED is handled)
        } catch (SecurityException e) {
            state = "perm_denied";
        } catch (Exception e) {
            state = "error";
        }
    }

    public synchronized void start() {
        try {
            BluetoothAdapter ad = mgr.getAdapter();
            if (ad == null || !ad.isEnabled()) { state = "bt_off"; return; }
            if (server != null) { try { server.close(); } catch (Exception e) { } server = null; }
            serviceReady = false; advertising = false; dev = null; notifying = false; outq.clear();
            server = mgr.openGattServer(ctx, cb);
            if (server == null) { state = "error"; return; }
            BluetoothGattService s = new BluetoothGattService(SVC, BluetoothGattService.SERVICE_TYPE_PRIMARY);
            BluetoothGattCharacteristic wc = new BluetoothGattCharacteristic(W,
                BluetoothGattCharacteristic.PROPERTY_WRITE | BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
                BluetoothGattCharacteristic.PERMISSION_WRITE);
            nc = new BluetoothGattCharacteristic(N, BluetoothGattCharacteristic.PROPERTY_NOTIFY, 0);
            nc.addDescriptor(new BluetoothGattDescriptor(CCCD,
                BluetoothGattDescriptor.PERMISSION_READ | BluetoothGattDescriptor.PERMISSION_WRITE));
            s.addCharacteristic(wc); s.addCharacteristic(nc);
            state = "starting";
            if (!server.addService(s)) state = "error";
        } catch (SecurityException e) {
            state = "perm_denied";
        } catch (Exception e) {
            state = "error";
        }
    }

    final AdvertiseCallback advCb = new AdvertiseCallback() {
        @Override public void onStartSuccess(AdvertiseSettings s) { advertising = true; if (dev == null) state = "advertising"; }
        @Override public void onStartFailure(int e) {
            if (e == AdvertiseCallback.ADVERTISE_FAILED_ALREADY_STARTED) { advertising = true; if (dev == null) state = "advertising"; }
            else { advertising = false; state = "adv_failed_" + e; }
        }
    };

    synchronized void advertise() {
        try {
            BluetoothAdapter ad = mgr.getAdapter();
            if (ad == null || !ad.isEnabled()) { state = "bt_off"; return; }
            BluetoothLeAdvertiser adv = ad.getBluetoothLeAdvertiser();
            if (adv == null) { state = "no_advertiser"; return; }
            AdvertiseSettings st = new AdvertiseSettings.Builder()
                .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY).setConnectable(true).setTimeout(0).build();
            AdvertiseData d = new AdvertiseData.Builder().setIncludeDeviceName(false).addServiceUuid(new ParcelUuid(SVC)).build();
            adv.startAdvertising(st, d, advCb);
        } catch (SecurityException e) {
            state = "perm_denied";
        } catch (Exception e) {
            state = "error";
        }
    }

    final BluetoothGattServerCallback cb = new BluetoothGattServerCallback() {
        @Override public void onServiceAdded(int st, BluetoothGattService s) {
            try {
                if (st == BluetoothGatt.GATT_SUCCESS) { serviceReady = true; advertise(); }
                else state = "error";
            } catch (Exception e) { state = "error"; }
        }
        @Override public void onConnectionStateChange(BluetoothDevice d, int st, int ns) {
            try {
                if (ns == BluetoothProfile.STATE_CONNECTED) {
                    dev = d; state = "connected"; notifying = false; notificationsEnabled = false; outq.clear();
                } else {
                    if (dev == null || d == null || d.getAddress().equals(dev.getAddress())) {
                        dev = null; notifying = false; notificationsEnabled = false; outq.clear(); mtu = 23;
                        state = "advertising"; advertising = false;
                        advertise();
                    }
                }
            } catch (Exception e) { state = "error"; }
        }
        @Override public void onMtuChanged(BluetoothDevice d, int m) { mtu = m; }
        @Override public void onCharacteristicWriteRequest(BluetoothDevice d, int id, BluetoothGattCharacteristic c,
                boolean prep, boolean resp, int off, byte[] v) {
            try {
                if (v != null) in.add(v);
                if (resp && server != null) server.sendResponse(d, id, BluetoothGatt.GATT_SUCCESS, 0, null);
            } catch (Exception e) { }
        }
        @Override public void onDescriptorWriteRequest(BluetoothDevice d, int id, BluetoothGattDescriptor ds,
                boolean prep, boolean resp, int off, byte[] v) {
            try {
                int result = BluetoothGatt.GATT_SUCCESS;
                if (ds == null || !CCCD.equals(ds.getUuid()) || v == null || off != 0 ||
                    !(java.util.Arrays.equals(v, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) ||
                      java.util.Arrays.equals(v, BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE))) {
                    result = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED;
                } else {
                    ds.setValue(v);
                    notificationsEnabled = java.util.Arrays.equals(v, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                    if (!notificationsEnabled) { synchronized (BleServer.this) { outq.clear(); } }
                }
                if (resp && server != null) server.sendResponse(d, id, result, 0, null);
            } catch (Exception e) {
                try { if (resp && server != null) server.sendResponse(d, id, BluetoothGatt.GATT_FAILURE, 0, null); } catch (Exception ignored) { }
            }
        }
        @Override public void onNotificationSent(BluetoothDevice d, int status) {
            synchronized (BleServer.this) {
                notifying = false;
                if (status == BluetoothGatt.GATT_SUCCESS) inFlight = null;
                else {
                    state = "notification_failed";
                    if (inFlight != null) outq.addFirst(inFlight);
                    inFlight = null;
                }
            }
            if (status != BluetoothGatt.GATT_SUCCESS) { main.postDelayed(pumpAgain, 250); return; }
            pumpNotify();
        }
    };

    final Runnable pumpAgain = new Runnable() { public void run() { pumpNotify(); } };

    public void notifyData(byte[] b) { outq.add(b); pumpNotify(); }

    synchronized void pumpNotify() {
        BluetoothDevice d = dev;
        if (d == null || nc == null || server == null || !notificationsEnabled) return;
        if (notifying && System.currentTimeMillis() - notifyT > 1500) {
            notifying = false;
            if (inFlight != null) outq.addFirst(inFlight);
            inFlight = null;
        } // recover a lost callback without dropping the fragment
        if (notifying) return;
        byte[] b = outq.poll();
        if (b == null) return;
        try {
            nc.setValue(b);
            inFlight = b;
            notifying = true; notifyT = System.currentTimeMillis();
            if (!server.notifyCharacteristicChanged(d, nc, false)) {
                notifying = false; inFlight = null; outq.addFirst(b); main.postDelayed(pumpAgain, 60);
            }
        } catch (Exception e) {
            notifying = false; inFlight = null; outq.addFirst(b); main.postDelayed(pumpAgain, 250);
        }
    }

    public byte[] poll() { return in.poll(); }
    public int chunkSize() { return Math.max(20, mtu - 3); }
    public String getState() { return state; }
}
