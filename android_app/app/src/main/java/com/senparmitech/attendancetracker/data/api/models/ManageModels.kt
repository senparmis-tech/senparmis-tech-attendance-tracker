package com.senparmitech.attendancetracker.data.api.models

import com.google.gson.annotations.SerializedName

data class StudentRow(
    val row: Int,
    val name: String,
    val student_no: String? = null,
    val guardian_name: String? = null,
    val guardian_phone: String? = null,
    val email: String? = null,
    val address: String? = null,
    val rate: Double? = null
)

data class StudentsResponse(
    val ok: Boolean,
    val subject: String = "",
    val section: String = "",
    val section_names: List<String> = emptyList(),
    val is_archived: Boolean = false,
    val term: String? = null,
    val term_locked: Boolean = false,
    val rows: List<StudentRow> = emptyList(),
    val error: String? = null
)

data class PeriodItem(
    val id: Int,
    val semester: String,
    val term: String,
    val label: String,
    val locked: Boolean = false,
    val locked_at: String? = null,
    val locked_by: String? = null,
    val n_dates: Int = 0,
    val n_items: Int = 0,
    val can_reopen: Boolean = false
)

data class PeriodsResponse(
    val ok: Boolean,
    val periods: List<PeriodItem> = emptyList(),
    val current_id: Int? = null,
    val next_semester: String = "",
    val next_term: String = "",
    val is_admin: Boolean = false,
    val error: String? = null
)

data class LogEntry(
    @SerializedName("when") val whenText: String = "",
    val action: String = "",
    val subject: String = "",
    val detail: String = "",
    val who: String = ""
)

data class LogResponse(
    val ok: Boolean,
    val total: Int = 0,
    val entries: List<LogEntry> = emptyList(),
    val error: String? = null
)

data class TeacherItem(
    val id: Int,
    val username: String,
    val display_name: String,
    val is_admin: Int = 0,
    val is_monitor: Int = 0,
    val n_subjects: Int = 0,
    val monitor_section_name: String? = null,
    val monitor_subject_name: String? = null
)

data class OwnedSubject(
    val name: String,
    val teacher_id: Int? = null
)

data class SectionOption(
    val id: Int,
    val section_name: String,
    val subject_name: String
)

data class TeachersResponse(
    val ok: Boolean,
    val is_admin: Boolean = false,
    val self_id: Int? = null,
    val teachers: List<TeacherItem> = emptyList(),
    val subjects: List<OwnedSubject> = emptyList(),
    val sections: List<SectionOption> = emptyList(),
    val error: String? = null
)
