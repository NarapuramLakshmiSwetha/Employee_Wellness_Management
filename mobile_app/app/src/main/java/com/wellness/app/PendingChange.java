package com.wellness.app;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

/**
 * Represents a mutation or data change that occurred while offline.
 * The payload should be a JSON string that the server can process.
 */
@Entity(tableName = "pending_changes")
public class PendingChange {
    @PrimaryKey(autoGenerate = true)
    public int id;

    @NonNull
    public String payload;

    public PendingChange(@NonNull String payload) {
        this.payload = payload;
    }
}
