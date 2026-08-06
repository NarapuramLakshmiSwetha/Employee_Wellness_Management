package com.wellness.app;

import androidx.room.Dao;
import androidx.room.Insert;
import androidx.room.OnConflictStrategy;
import androidx.room.Query;
import java.util.List;

@Dao
public interface CachedResponseDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    void insert(CachedResponse response);

    @Query("SELECT * FROM cached_responses WHERE `key` = :key LIMIT 1")
    CachedResponse getByKey(String key);

    @Query("SELECT * FROM cached_responses")
    List<CachedResponse> getAll();

    @Query("DELETE FROM cached_responses WHERE `key` = :key")
    void deleteByKey(String key);

    @Query("DELETE FROM cached_responses")
    void clearAll();
}
