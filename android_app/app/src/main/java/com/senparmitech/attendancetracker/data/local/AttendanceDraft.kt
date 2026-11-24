package com.senparmitech.attendancetracker.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "attendance_drafts")
data class AttendanceDraft(
    @PrimaryKey
    val key: String, // composite key: "$subject-$section-$date"
    val subject: String,
    val section: String,
    val dateIso: String,
    val topic: String,
    val marksJson: String, // JSON string of List<MarkSubmissionItem>
    val lastUpdated: Long = System.currentTimeMillis()
)
