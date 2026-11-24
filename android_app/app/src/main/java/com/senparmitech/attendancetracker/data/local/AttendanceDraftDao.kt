package com.senparmitech.attendancetracker.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface AttendanceDraftDao {

    @Query("SELECT * FROM attendance_drafts WHERE `key` = :key LIMIT 1")
    suspend fun getDraft(key: String): AttendanceDraft?

    @Query("SELECT * FROM attendance_drafts WHERE `key` = :key LIMIT 1")
    fun observeDraft(key: String): Flow<AttendanceDraft?>

    @Query("SELECT * FROM attendance_drafts ORDER BY lastUpdated DESC")
    suspend fun getAllDrafts(): List<AttendanceDraft>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveDraft(draft: AttendanceDraft)

    @Query("DELETE FROM attendance_drafts WHERE `key` = :key")
    suspend fun deleteDraft(key: String)

    @Query("DELETE FROM attendance_drafts")
    suspend fun clearAllDrafts()
}
