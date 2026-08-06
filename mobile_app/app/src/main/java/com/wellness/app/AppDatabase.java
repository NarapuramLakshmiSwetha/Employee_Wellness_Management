package com.wellness.app;

import androidx.room.Database;
import androidx.room.RoomDatabase;

/**
 * Central Room database for the wellness app.
 * Includes cached API responses and pending offline mutations.
 */
@Database(entities = {CachedResponse.class, PendingChange.class}, version = 1, exportSchema = false)
public abstract class AppDatabase extends RoomDatabase {
    public abstract CachedResponseDao cachedResponseDao();
    public abstract PendingChangeDao pendingChangeDao();
}
