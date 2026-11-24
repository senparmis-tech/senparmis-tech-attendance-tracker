package com.senparmitech.attendancetracker.data.repository

import com.google.gson.JsonParser
import com.senparmitech.attendancetracker.data.api.AttendanceApiService
import com.senparmitech.attendancetracker.data.api.models.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import retrofit2.Response

/** Calls for the management screens: students, grade setup, terms, activity log and accounts. */
class ManageRepository(private val provider: () -> AttendanceApiService) {

    private val api: AttendanceApiService get() = provider()

    private fun serverError(resp: Response<*>): String? {
        val raw = try { resp.errorBody()?.string() } catch (e: Exception) { null } ?: return null
        return try { JsonParser.parseString(raw).asJsonObject.get("error").asString } catch (e: Exception) { null }
    }

    /** POST an action. Returns null on success, otherwise the message to show. */
    suspend fun act(path: String, vararg fields: Pair<String, Any?>): String? = withContext(Dispatchers.IO) {
        try {
            val resp = api.action(path, mapOf(*fields))
            if (resp.isSuccessful && resp.body()?.ok == true) null
            else serverError(resp) ?: resp.body()?.error ?: "That did not work. Please try again."
        } catch (e: Exception) {
            e.message ?: "Could not reach the server."
        }
    }

    private suspend fun <T> load(what: String, call: suspend () -> Response<T>, ok: (T) -> Boolean): Result<T> =
        withContext(Dispatchers.IO) {
            try {
                val resp = call()
                val body = resp.body()
                if (resp.isSuccessful && body != null && ok(body)) Result.success(body)
                else Result.failure(Exception(serverError(resp) ?: "Could not load $what."))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun students(subject: String, section: String?) =
        load("students", { api.getStudents(subject, section) }, { it.ok })

    suspend fun periods(subject: String, section: String?) =
        load("terms", { api.getPeriods(subject, section) }, { it.ok })

    suspend fun log() = load("the activity log", { api.getLog() }, { it.ok })

    suspend fun teachers() = load("accounts", { api.getTeachers() }, { it.ok })
}
