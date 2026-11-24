package com.senparmitech.attendancetracker.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [AttendanceDraft::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {

    abstract fun draftDao(): AttendanceDraftDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "attendance_local.db"
                ).build()
                INSTANCE = instance
                instance
            }
        }
    }
}
