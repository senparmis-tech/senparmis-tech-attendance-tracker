package com.senparmitech.attendancetracker.data.api

import com.senparmitech.attendancetracker.data.api.models.*
import retrofit2.Response
import retrofit2.http.*

interface AttendanceApiService {

    @POST("/api/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @GET("/api/me")
    suspend fun getCurrentUser(): Response<UserProfileResponse>

    @POST("/api/logout")
    suspend fun logout(): Response<ApiResponse>

    @GET("/api/dashboard")
    suspend fun getDashboard(): Response<DashboardResponse>

    @GET("/api/subjects")
    suspend fun getSubjects(): Response<SubjectsResponse>

    @GET("/api/mark")
    suspend fun getAttendanceRoster(
        @Query("subject") subject: String,
        @Query("section") section: String? = null,
        @Query("date") date: String? = null
    ): Response<MarkAttendanceResponse>

    @POST("/api/save")
    suspend fun saveAttendance(@Body request: SaveAttendanceRequest): Response<ApiResponse>

    @GET("/api/records")
    suspend fun getRecords(
        @Query("subject") subject: String,
        @Query("section") section: String? = null
    ): Response<RecordsResponse>

    @GET("/api/grades")
    suspend fun getGrades(
        @Query("subject") subject: String,
        @Query("section") section: String? = null
    ): Response<GradebookResponse>

    @POST("/api/subject_archive")
    suspend fun archiveSubject(@Body request: ArchiveRequest): Response<ApiResponse>

    @POST("/api/subject_unarchive")
    suspend fun unarchiveSubject(@Body request: ArchiveRequest): Response<ApiResponse>

    @POST("/api/grade_score")
    suspend fun saveGradeScore(@Body request: GradeScoreRequest): Response<ApiResponse>

    @GET("/api/lookup")
    suspend fun searchStudents(
        @Query("q") query: String
    ): Response<LookupResponse>

    // ---- management screens ----

    @GET("/api/students")
    suspend fun getStudents(
        @Query("subject") subject: String,
        @Query("section") section: String? = null
    ): Response<StudentsResponse>

    @GET("/api/periods")
    suspend fun getPeriods(
        @Query("subject") subject: String,
        @Query("section") section: String? = null
    ): Response<PeriodsResponse>

    @GET("/api/log")
    suspend fun getLog(): Response<LogResponse>

    @GET("/api/teachers")
    suspend fun getTeachers(): Response<TeachersResponse>

    /** Any of the POST actions that only answer ok / error (add student, lock term, set weights, ...). */
    @POST
    suspend fun action(
        @Url path: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>
    ): Response<ApiResponse>
}
