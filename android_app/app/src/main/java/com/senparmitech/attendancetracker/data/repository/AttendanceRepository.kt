package com.senparmitech.attendancetracker.data.repository

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.senparmitech.attendancetracker.data.api.AttendanceApiService
import com.senparmitech.attendancetracker.data.api.SessionManager
import com.senparmitech.attendancetracker.data.api.models.*
import com.senparmitech.attendancetracker.data.local.AttendanceDraft
import com.senparmitech.attendancetracker.data.local.AttendanceDraftDao
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import retrofit2.Response

class AttendanceRepository(
    private val apiServiceProvider: () -> AttendanceApiService,
    private val draftDao: AttendanceDraftDao,
    private val sessionManager: SessionManager
) {
    // Looked up on every call, so a changed server URL takes effect without restarting the app.
    private val apiService: AttendanceApiService get() = apiServiceProvider()

    private val gson = Gson()

    /** The server's own message for a failed request (its JSON "error" field), if it sent one. */
    private fun serverError(resp: Response<*>): String? {
        val raw = try { resp.errorBody()?.string() } catch (e: Exception) { null } ?: return null
        return try { com.google.gson.JsonParser.parseString(raw).asJsonObject.get("error").asString } catch (e: Exception) { null }
    }

    suspend fun login(password: String, username: String = ""): Result<LoginResponse> =
        withContext(Dispatchers.IO) {
            try {
                val resp = apiService.login(LoginRequest(username = username, password = password))
                if (resp.isSuccessful && resp.body()?.ok == true) {
                    val body = resp.body()!!
                    sessionManager.saveCredentials(username, password)
                    sessionManager.saveUser(
                        role = body.role ?: "teacher",
                        displayName = body.display_name ?: "Faculty",
                        username = body.username ?: username,
                        isAdmin = body.is_admin,
                        isMonitor = body.is_monitor,
                        monitorSectionId = body.monitor_section_id
                    )
                    Result.success(body)
                } else {
                    val errMsg = resp.body()?.error ?: serverError(resp) ?: "Sign-in failed. Please check credentials."
                    Result.failure(Exception(errMsg))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun logout(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            apiService.logout()
            sessionManager.clearSession()
            Result.success(Unit)
        } catch (e: Exception) {
            sessionManager.clearSession()
            Result.success(Unit)
        }
    }

    suspend fun getMe(): Result<UserProfileResponse> = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.getCurrentUser()
            if (resp.isSuccessful && resp.body()?.ok == true) {
                Result.success(resp.body()!!)
            } else {
                Result.failure(Exception("Failed to fetch user profile"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getDashboard(): Result<DashboardResponse> = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.getDashboard()
            if (resp.isSuccessful && resp.body()?.ok == true) {
                Result.success(resp.body()!!)
            } else {
                Result.failure(Exception("Could not load dashboard data."))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getSubjects(): Result<SubjectsResponse> = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.getSubjects()
            if (resp.isSuccessful && resp.body()?.ok == true) {
                Result.success(resp.body()!!)
            } else {
                Result.failure(Exception("Could not load subjects."))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getAttendanceRoster(
        subject: String,
        section: String? = null,
        date: String? = null
    ): Result<MarkAttendanceResponse> = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.getAttendanceRoster(subject, section, date)
            if (resp.isSuccessful && resp.body()?.ok == true) {
                val body = resp.body()!!
                // Check if an offline draft exists for this subject-section-date
                val draftKey = "$subject-${section ?: "BSCS-1A"}-${body.date_iso}"
                val localDraft = draftDao.getDraft(draftKey)
                if (localDraft != null) {
                    val type = object : TypeToken<List<MarkSubmissionItem>>() {}.type
                    val draftMarks: List<MarkSubmissionItem> = gson.fromJson(localDraft.marksJson, type)
                    val markMap = draftMarks.associateBy({ it.name }, { it.code })
                    val updatedStudents = body.students.map { s ->
                        val code = markMap[s.name] ?: s.code
                        s.copy(code = code)
                    }
                    Result.success(
                        body.copy(
                            topic = if (localDraft.topic.isNotBlank()) localDraft.topic else body.topic,
                            students = updatedStudents
                        )
                    )
                } else {
                    Result.success(body)
                }
            } else {
                val err = resp.body()?.error ?: "Could not load roster."
                Result.failure(Exception(err))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun saveDraftLocally(
        subject: String,
        section: String,
        dateIso: String,
        topic: String,
        marks: List<MarkSubmissionItem>
    ) = withContext(Dispatchers.IO) {
        val draftKey = "$subject-$section-$dateIso"
        val json = gson.toJson(marks)
        draftDao.saveDraft(
            AttendanceDraft(
                key = draftKey,
                subject = subject,
                section = section,
                dateIso = dateIso,
                topic = topic,
                marksJson = json
            )
        )
    }

    suspend fun submitAttendance(
        subject: String,
        section: String,
        dateIso: String,
        topic: String,
        marks: List<MarkSubmissionItem>
    ): Result<Unit> = withContext(Dispatchers.IO) {
        val draftKey = "$subject-$section-$dateIso"
        try {
            // First save locally as a draft to ensure offline safety
            saveDraftLocally(subject, section, dateIso, topic, marks)

            val req = SaveAttendanceRequest(
                subject = subject,
                section = section,
                date = dateIso,
                topic = topic,
                marks = marks
            )
            val resp = apiService.saveAttendance(req)
            if (resp.isSuccessful && resp.body()?.ok == true) {
                // Remove local draft once confirmed by server
                draftDao.deleteDraft(draftKey)
                Result.success(Unit)
            } else {
                val err = resp.body()?.error ?: "Failed to save on server."
                Result.failure(Exception(err))
            }
        } catch (e: Exception) {
            // If network fails, local draft remains safely persisted in Room
            Result.failure(e)
        }
    }

    suspend fun getRecords(subject: String, section: String? = null): Result<RecordsResponse> =
        withContext(Dispatchers.IO) {
            try {
                val resp = apiService.getRecords(subject, section)
                if (resp.isSuccessful && resp.body()?.ok == true) {
                    Result.success(resp.body()!!)
                } else {
                    Result.failure(Exception(serverError(resp) ?: "Could not load attendance records."))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun getGrades(subject: String, section: String? = null): Result<GradebookResponse> =
        withContext(Dispatchers.IO) {
            try {
                val resp = apiService.getGrades(subject, section)
                if (resp.isSuccessful && resp.body()?.ok == true) {
                    Result.success(resp.body()!!)
                } else {
                    Result.failure(Exception(serverError(resp) ?: "Could not load gradebook."))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun searchStudents(query: String): Result<LookupResponse> =
        withContext(Dispatchers.IO) {
            try {
                val resp = apiService.searchStudents(query)
                if (resp.isSuccessful && resp.body()?.ok == true) {
                    Result.success(resp.body()!!)
                } else {
                    Result.failure(Exception("Search failed."))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /** Archive a subject. Returns null on success, otherwise the message to show. */
    suspend fun archiveSubject(name: String, note: String): String? = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.archiveSubject(ArchiveRequest(name, note))
            if (resp.isSuccessful && resp.body()?.ok == true) null
            else serverError(resp) ?: "Could not archive '$name'."
        } catch (e: Exception) {
            e.message ?: "Could not reach the server."
        }
    }

    /** Restore an archived subject. Returns null on success, otherwise the message to show. */
    suspend fun unarchiveSubject(name: String): String? = withContext(Dispatchers.IO) {
        try {
            val resp = apiService.unarchiveSubject(ArchiveRequest(name))
            if (resp.isSuccessful && resp.body()?.ok == true) null
            else serverError(resp) ?: "Could not restore '$name'."
        } catch (e: Exception) {
            e.message ?: "Could not reach the server."
        }
    }

    /**
     * Save changed scores for one student, one item at a time (the server checks each against
     * the item's maximum). Returns null when all were saved, otherwise the message to show.
     */
    suspend fun saveScores(
        subject: String,
        section: String?,
        enrollmentId: Int,
        changes: List<Pair<Int, Double?>>
    ): String? = withContext(Dispatchers.IO) {
        try {
            for ((itemId, score) in changes) {
                val resp = apiService.saveGradeScore(
                    GradeScoreRequest(subject, section, itemId, enrollmentId, score)
                )
                if (!(resp.isSuccessful && resp.body()?.ok == true)) {
                    return@withContext serverError(resp) ?: "Could not save the score."
                }
            }
            null
        } catch (e: Exception) {
            e.message ?: "Could not reach the server."
        }
    }
}
