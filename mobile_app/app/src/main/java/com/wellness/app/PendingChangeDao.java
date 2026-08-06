package com.wellness.app;

import androidx.annotation.NonNull;
import androidx.room.Dao;
import androidx.room.Insert;
import androidx.room.Query;
import androidx.room.Delete;
import java.util.List;

@Dao
public interface PendingChangeDao {
    @Insert
    void insert(PendingChange change);

    @Query("SELECT * FROM pending_changes")
    List<PendingChange> getAll();

    @Delete
    void delete(PendingChange change);
}
