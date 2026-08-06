package com.wellness.app;

import android.content.Context;
import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.util.List;

/**
 * Worker that synchronizes pending offline changes with the remote Flask server when network is available.
 * It reads all {@link PendingChange} entries from the Room database, attempts to POST them to the server,
 * and removes successfully synced items.
 */
public class SyncWorker extends Worker {

    private AppDatabase appDatabase;
    private static final String SERVER_URL = "http://127.0.0.1:5000/api/sync"; // adjust endpoint as needed

    public SyncWorker(@NonNull Context context, @NonNull WorkerParameters workerParams) {
        super(context, workerParams);
        appDatabase = androidx.room.Room.databaseBuilder(context, AppDatabase.class, "wellness-db").build();
    }

    @NonNull
    @Override
    public Result doWork() {
        try {
            PendingChangeDao pendingDao = appDatabase.pendingChangeDao();
            List<PendingChange> pendingChanges = pendingDao.getAll();
            if (pendingChanges.isEmpty()) {
                return Result.success();
            }
            for (PendingChange change : pendingChanges) {
                // Simple HTTP POST; in a real app use OkHttp/Retrofit with proper JSON handling.
                boolean success = HttpUtil.postJson(SERVER_URL, change.getPayload());
                if (success) {
                    pendingDao.delete(change);
                } else {
                    // If any upload fails, we retry later.
                    return Result.retry();
                }
            }
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.retry();
        }
    }
}
