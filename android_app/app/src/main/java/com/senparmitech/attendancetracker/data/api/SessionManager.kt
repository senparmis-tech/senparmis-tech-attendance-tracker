package com.senparmitech.attendancetracker.data.api

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class SessionManager(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val _serverUrlState = MutableStateFlow(getServerUrl())
    val serverUrlState: StateFlow<String> = _serverUrlState.asStateFlow()

    private val _isLoggedInState = MutableStateFlow(isLoggedIn())
    val isLoggedInState: StateFlow<Boolean> = _isLoggedInState.asStateFlow()

    fun getServerUrl(): String {
        return prefs.getString(KEY_SERVER_URL, DEFAULT_URL) ?: DEFAULT_URL
    }

    fun setServerUrl(url: String) {
        var cleanUrl = url.trim()
        if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
            cleanUrl = "http://$cleanUrl"
        }
        if (cleanUrl.endsWith("/")) {
            cleanUrl = cleanUrl.substring(0, cleanUrl.length - 1)
        }
        prefs.edit().putString(KEY_SERVER_URL, cleanUrl).apply()
        _serverUrlState.value = cleanUrl
        ApiClient.resetClient()
    }

    fun saveCookies(cookies: Set<String>) {
        prefs.edit().putStringSet(KEY_COOKIES, cookies).apply()
    }

    fun getCookies(): Set<String> {
        return prefs.getStringSet(KEY_COOKIES, emptySet()) ?: emptySet()
    }

    fun saveUser(
        role: String,
        displayName: String,
        username: String,
        isAdmin: Boolean,
        isMonitor: Boolean,
        monitorSectionId: Int?
    ) {
        prefs.edit()
            .putString(KEY_ROLE, role)
            .putString(KEY_DISPLAY_NAME, displayName)
            .putString(KEY_USERNAME, username)
            .putBoolean(KEY_IS_ADMIN, isAdmin)
            .putBoolean(KEY_IS_MONITOR, isMonitor)
            .putInt(KEY_MONITOR_SEC_ID, monitorSectionId ?: -1)
            .putBoolean(KEY_IS_LOGGED_IN, true)
            .apply()

        _isLoggedInState.value = true
    }

    fun isLoggedIn(): Boolean {
        return prefs.getBoolean(KEY_IS_LOGGED_IN, false)
    }

    fun getUserRole(): String = prefs.getString(KEY_ROLE, "") ?: ""
    fun getDisplayName(): String = prefs.getString(KEY_DISPLAY_NAME, "") ?: ""
    fun getUsername(): String = prefs.getString(KEY_USERNAME, "") ?: ""
    fun isAdmin(): Boolean = prefs.getBoolean(KEY_IS_ADMIN, false)
    fun isMonitor(): Boolean = prefs.getBoolean(KEY_IS_MONITOR, false)
    fun getMonitorSectionId(): Int? {
        val id = prefs.getInt(KEY_MONITOR_SEC_ID, -1)
        return if (id != -1) id else null
    }

    fun clearSession() {
        prefs.edit()
            .remove(KEY_COOKIES)
            .remove(KEY_ROLE)
            .remove(KEY_DISPLAY_NAME)
            .remove(KEY_USERNAME)
            .remove(KEY_IS_ADMIN)
            .remove(KEY_IS_MONITOR)
            .remove(KEY_MONITOR_SEC_ID)
            .putBoolean(KEY_IS_LOGGED_IN, false)
            .apply()

        _isLoggedInState.value = false
    }

    companion object {
        private const val PREFS_NAME = "senparmis_attendance_prefs"
        private const val KEY_SERVER_URL = "key_server_url"
        private const val KEY_COOKIES = "key_cookies"
        private const val KEY_IS_LOGGED_IN = "key_is_logged_in"
        private const val KEY_ROLE = "key_role"
        private const val KEY_DISPLAY_NAME = "key_display_name"
        private const val KEY_USERNAME = "key_username"
        private const val KEY_IS_ADMIN = "key_is_admin"
        private const val KEY_IS_MONITOR = "key_is_monitor"
        private const val KEY_MONITOR_SEC_ID = "key_monitor_sec_id"

        const val DEFAULT_URL = "http://10.0.2.2:5000"
    }
}
