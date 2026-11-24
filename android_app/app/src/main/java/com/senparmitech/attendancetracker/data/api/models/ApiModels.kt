package com.senparmitech.attendancetracker.data.api.models

import com.google.gson.annotations.SerializedName

// Generic API response
data class ApiResponse(
    val ok: Boolean,
    val error: String? = null,
    val message: String? = null
)

// Login Request & Response
data class LoginRequest(
    val username: String = "",
    val password: String
)

data class LoginResponse(
    val ok: Boolean,
    val role: String? = null,
    val teacher_id: Int? = null,
    val username: String? = null,
    val display_name: String? = null,
    val is_admin: Boolean = false,
    val is_monitor: Boolean = false,
    val monitor_section_id: Int? = null,
    val error: String? = null
)

// Current User Profile
data class UserProfileResponse(
    val ok: Boolean,
    val authenticated: Boolean = false,
    val role: String? = null,
    val teacher_id: Int? = null,
    val display_name: String? = null,
    val is_admin: Boolean = false,
    val is_monitor: Boolean = false,
    val monitor_section_id: Int? = null,
    val monitor_section_name: String? = null
)

// Dashboard
data class DashboardOverview(
    val total_students: Int = 0,
    val total_subjects: Int = 0,
    val total_sections: Int = 0,
    val completed_sessions: Int = 0,
    val pending_rollcalls: Int = 0,
    val low_attendance_count: Int = 0
)

data class DashboardCard(
    val subject: String,
    val section: String,
    val n_students: Int = 0,
    val held: Int = 0,
    val avg: Double? = null,
    val today_recorded: Boolean = false,
    val today_counts: AttendanceCounts? = null,
    val absent_today: List<String> = emptyList(),
    val watch_count: Int = 0,
    val image_url: String? = null
)

data class AttendanceCounts(
    val p: Int = 0,
    val x: Int = 0,
    val l: Int = 0,
    val e: Int = 0,
    val r: Int = 0
)

data class DashboardResponse(
    val ok: Boolean,
    val today_iso: String,
    val today_label: String,
    val overview: DashboardOverview,
    val cards: List<DashboardCard> = emptyList()
)

// Subjects List
data class SubjectItem(
    val name: String,
    val sections: List<String> = emptyList(),
    val n_students: Int = 0,
    val image_url: String? = null,
    val archived: Boolean = false
)

data class ArchivedSubjectItem(
    val id: Int,
    val name: String,
    val archived_at: String? = null,
    val archive_note: String? = null,
    val n_students: Int = 0
)

data class SubjectsResponse(
    val ok: Boolean,
    val subjects: List<SubjectItem> = emptyList(),
    val archived_subjects: List<ArchivedSubjectItem> = emptyList()
)

// Mark Attendance
data class StudentRosterItem(
    val row: Int,
    val name: String,
    var code: String = "p"
)

data class MarkAttendanceResponse(
    val ok: Boolean,
    val subject: String,
    val section: String,
    val date_iso: String,
    val date_label: String,
    val recorded: Boolean = false,
    val topic: String? = null,
    val students: List<StudentRosterItem> = emptyList(),
    val error: String? = null
)

data class MarkSubmissionItem(
    val row: Int,
    val name: String,
    val code: String
)

data class SaveAttendanceRequest(
    val subject: String,
    val section: String? = null,
    val date: String,
    val topic: String = "",
    val marks: List<MarkSubmissionItem>
)

// Records Matrix
data class RecordDate(
    val id: Int,
    val label: String,
    val iso: String,
    val topic: String? = null
)

data class RecordRow(
    val row: Int,
    val name: String,
    val student_no: String? = null,
    val p: Int = 0,
    val x: Int = 0,
    val l: Int = 0,
    val e: Int = 0,
    val r: Int = 0,
    val rate: Double? = null,
    val codes: List<String> = emptyList()
)

data class RecordsResponse(
    val ok: Boolean,
    val subject: String,
    val section: String,
    val is_archived: Boolean = false,
    val dates: List<RecordDate> = emptyList(),
    val rows: List<RecordRow> = emptyList(),
    val error: String? = null
)

// Gradebook
data class GradeItem(
    val id: Int,
    val category: String,
    val label: String,
    val title: String,
    val max_score: Double
)

data class GradeWeights(
    val exam: Double = 50.0,
    val quiz: Double = 30.0,
    val activity: Double = 20.0
)

data class GradebookStudentRow(
    val enrollment_id: Int,
    val name: String,
    val student_no: String? = null,
    val scores: Map<String, Double?> = emptyMap(),
    val cat_pct: Map<String, Double?> = emptyMap(),
    val final_pct: Double? = null,
    val scale: String? = null,
    val passing: Boolean? = null
)

data class GradebookResponse(
    val ok: Boolean,
    val subject: String,
    val section: String,
    val is_archived: Boolean = false,
    val weights: GradeWeights = GradeWeights(),
    val locked: Boolean = false,
    val items: List<GradeItem> = emptyList(),
    val rows: List<GradebookStudentRow> = emptyList(),
    val error: String? = null
)

// Student Lookup
data class StudentLookupSubject(
    val subject: String,
    val section: String,
    val rate: Double? = null,
    val final_pct: Double? = null,
    val scale: String? = null
)

data class StudentLookupProfile(
    val name: String,
    val student_no: String? = null,
    val guardian_name: String? = null,
    val guardian_phone: String? = null,
    val email: String? = null,
    val sections: List<String> = emptyList(),
    val subjects: List<StudentLookupSubject> = emptyList()
)

data class LookupResponse(
    val ok: Boolean,
    val query: String,
    val total_matches: Int = 0,
    val results: List<StudentLookupProfile> = emptyList()
)
