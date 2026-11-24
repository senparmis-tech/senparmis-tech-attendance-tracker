package com.senparmitech.attendancetracker

import android.app.Application
import com.senparmitech.attendancetracker.data.api.ApiClient
import com.senparmitech.attendancetracker.data.api.SessionManager
import com.senparmitech.attendancetracker.data.local.AppDatabase
import com.senparmitech.attendancetracker.data.repository.AttendanceRepository

class AttendanceApp : Application() {

    lateinit var sessionManager: SessionManager
        private set

    lateinit var database: AppDatabase
        private set

    lateinit var repository: AttendanceRepository
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this

        sessionManager = SessionManager(this)
        database = AppDatabase.getInstance(this)

        repository = AttendanceRepository(
            { ApiClient.getApiService(sessionManager) },
            database.draftDao(),
            sessionManager
        )
    }

    companion object {
        lateinit var instance: AttendanceApp
            private set
    }
}
