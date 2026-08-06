package com.wellness.app;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.PrimaryKey;

/**
 * Cached response for offline reads.
 */
@Entity(tableName = "cached_responses")
public class CachedResponse {
    @PrimaryKey
    @NonNull
    public String key;

    public String value;

    public long timestamp;

    public CachedResponse(@NonNull String key, String value, long timestamp) {
        this.key = key;
        this.value = value;
        this.timestamp = timestamp;
    }
}
