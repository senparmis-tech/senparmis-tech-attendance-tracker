package com.senparmitech.attendancetracker.ui.screens

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.MarkSubmissionItem
import com.senparmitech.attendancetracker.data.api.models.StudentRosterItem
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun MarkAttendanceScreen(
    initialSubject: String? = null,
    initialSection: String? = null,
    initialDate: String? = null,
    onNavigateBack: () -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var subject by remember { mutableStateOf(initialSubject ?: "") }
    var section by remember { mutableStateOf(initialSection ?: "") }
    var dateIso by remember { mutableStateOf(initialDate ?: "") }
    var dateLabel by remember { mutableStateOf("") }
    var topic by remember { mutableStateOf("") }
    var students by remember { mutableStateOf<List<StudentRosterItem>>(emptyList()) }
    var searchQuery by remember { mutableStateOf("") }
    var filterCode by remember { mutableStateOf<String?>(null) } // null = All, or "p", "x", etc.

    var isLoading by remember { mutableStateOf(true) }
    var isSaving by remember { mutableStateOf(false) }
    var hasUnsavedChanges by remember { mutableStateOf(false) }

    fun loadRoster() {
        if (subject.isBlank()) return
        isLoading = true
        scope.launch {
            val result = repository.getAttendanceRoster(subject, section.ifBlank { null }, dateIso.ifBlank { null })
            isLoading = false
            if (result.isSuccess) {
                val data = result.getOrNull()!!
                subject = data.subject
                section = data.section
                dateIso = data.date_iso
                dateLabel = data.date_label
                topic = data.topic ?: ""
                students = data.students
                hasUnsavedChanges = false
            } else {
                Toast.makeText(context, result.exceptionOrNull()?.message ?: "Error loading roster", Toast.LENGTH_SHORT).show()
            }
        }
    }

    LaunchedEffect(subject, section, dateIso) {
        if (subject.isNotBlank()) {
            loadRoster()
        } else {
            // Fetch first available subject
            scope.launch {
                val subResult = repository.getSubjects()
                if (subResult.isSuccess && subResult.getOrNull()?.subjects?.isNotEmpty() == true) {
                    val firstSub = subResult.getOrNull()!!.subjects.first()
                    subject = firstSub.name
                    section = firstSub.sections.firstOrNull() ?: "BSCS-1A"
                    loadRoster()
                } else {
                    isLoading = false
                }
            }
        }
    }

    fun updateStudentCode(row: Int, code: String) {
        students = students.map { if (it.row == row) it.copy(code = code) else it }
        hasUnsavedChanges = true
        // Automatically save local draft in Room
        scope.launch {
            val marks = students.map { MarkSubmissionItem(it.row, it.name, it.code) }
            repository.saveDraftLocally(subject, section, dateIso, topic, marks)
        }
    }

    fun markAllPresent() {
        students = students.map { it.copy(code = "p") }
        hasUnsavedChanges = true
        scope.launch {
            val marks = students.map { MarkSubmissionItem(it.row, it.name, it.code) }
            repository.saveDraftLocally(subject, section, dateIso, topic, marks)
        }
    }

    fun saveAttendance() {
        if (isSaving) return
        isSaving = true
        scope.launch {
            val marks = students.map { MarkSubmissionItem(it.row, it.name, it.code) }
            val result = repository.submitAttendance(subject, section, dateIso, topic, marks)
            isSaving = false
            if (result.isSuccess) {
                hasUnsavedChanges = false
                Toast.makeText(context, "Attendance saved successfully!", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(context, result.exceptionOrNull()?.message ?: "Failed to save on server.", Toast.LENGTH_LONG).show()
            }
        }
    }

    // Counts
    val countP = students.count { it.code.lowercase() == "p" }
    val countX = students.count { it.code.lowercase() == "x" }
    val countL = students.count { it.code.lowercase() == "l" }
    val countE = students.count { it.code.lowercase() == "e" }
    val countR = students.count { it.code.lowercase() == "r" }

    // Filtered list
    val filteredStudents = students.filter { s ->
        val matchesSearch = searchQuery.isBlank() || s.name.contains(searchQuery, ignoreCase = true)
        val matchesCode = filterCode == null || s.code.lowercase() == filterCode!!.lowercase()
        matchesSearch && matchesCode
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Mark Attendance",
                subtitle = if (subject.isNotBlank()) "$subject · $section" else "Daily Roll Call",
                actions = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Slate400)
                    }
                }
            )
        },
        bottomBar = {
            // Floating Mobile Action Dock
            Surface(
                color = Navy900,
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .navigationBarsPadding()
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        CountBadge("P $countP", PresentBg, PresentGreen)
                        CountBadge("A $countX", AbsentBg, AbsentRed)
                        CountBadge("L $countL", LateBg, LateYellow)
                        CountBadge("E $countE", ExcusedBg, ExcusedBlue)
                        CountBadge("R $countR", RecitedBg, RecitedPurple)
                    }

                    Button(
                        onClick = { saveAttendance() },
                        enabled = !isSaving,
                        colors = ButtonDefaults.buttonColors(containerColor = if (hasUnsavedChanges) LateYellow else Blue600),
                        shape = RoundedCornerShape(6.dp),
                        modifier = Modifier.height(42.dp)
                    ) {
                        if (isSaving) {
                            CircularProgressIndicator(color = Slate50, modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                        } else {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(7.dp)
                                        .background(if (hasUnsavedChanges) Color(0xFFF59E0B) else Color(0xFF22C55E), CircleShape)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("Save", fontWeight = FontWeight.Bold, fontSize = 13.5.sp)
                            }
                        }
                    }
                }
            }
        },
        containerColor = Navy950
    ) { padding ->
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Blue500)
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
            ) {
                // Header date & topic card
                Card(
                    colors = CardDefaults.cardColors(containerColor = Navy900),
                    shape = RoundedCornerShape(0.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = dateLabel.ifBlank { dateIso },
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp,
                                color = Slate50
                            )
                            Button(
                                onClick = { markAllPresent() },
                                colors = ButtonDefaults.buttonColors(containerColor = Navy800),
                                shape = RoundedCornerShape(4.dp),
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                modifier = Modifier.height(32.dp)
                            ) {
                                Text("All Present", fontSize = 11.5.sp, color = PresentGreen, fontWeight = FontWeight.Bold)
                            }
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = topic,
                            onValueChange = {
                                topic = it
                                hasUnsavedChanges = true
                            },
                            placeholder = { Text("Lesson topic or summary (optional)", fontSize = 12.sp) },
                            singleLine = true,
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = Blue500,
                                unfocusedBorderColor = Slate800,
                                focusedTextColor = Slate50,
                                unfocusedTextColor = Slate50
                            ),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }

                // Search & Filter Bar
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        placeholder = { Text("Search student name...", fontSize = 12.sp) },
                        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Slate400, modifier = Modifier.size(16.dp)) },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Blue500,
                            unfocusedBorderColor = Slate800,
                            focusedTextColor = Slate50,
                            unfocusedTextColor = Slate50
                        ),
                        modifier = Modifier.weight(1f)
                    )
                }

                // Filter Pills Row
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 2.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    FilterPill("All", filterCode == null) { filterCode = null }
                    FilterPill("P", filterCode == "p", PresentGreen) { filterCode = "p" }
                    FilterPill("A", filterCode == "x", AbsentRed) { filterCode = "x" }
                    FilterPill("L", filterCode == "l", LateYellow) { filterCode = "l" }
                    FilterPill("E", filterCode == "e", ExcusedBlue) { filterCode = "e" }
                    FilterPill("R", filterCode == "r", RecitedPurple) { filterCode = "r" }
                }

                Spacer(modifier = Modifier.height(6.dp))

                // Students Roster List
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .padding(horizontal = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(bottom = 14.dp)
                ) {
                    items(filteredStudents, key = { it.row }) { s ->
                        StudentMarkRow(
                            student = s,
                            onCodeSelected = { code -> updateStudentCode(s.row, code) }
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun StudentMarkRow(
    student: StudentRosterItem,
    onCodeSelected: (String) -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Navy900),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Text(
                text = student.name,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                color = Slate50
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                CodeButton("P", "Present", student.code == "p", PresentBg, PresentGreen, Modifier.weight(1f)) { onCodeSelected("p") }
                CodeButton("A", "Absent", student.code == "x", AbsentBg, AbsentRed, Modifier.weight(1f)) { onCodeSelected("x") }
                CodeButton("L", "Late", student.code == "l", LateBg, LateYellow, Modifier.weight(1f)) { onCodeSelected("l") }
                CodeButton("E", "Excused", student.code == "e", ExcusedBg, ExcusedBlue, Modifier.weight(1f)) { onCodeSelected("e") }
                CodeButton("R", "Recited", student.code == "r", RecitedBg, RecitedPurple, Modifier.weight(1f)) { onCodeSelected("r") }
            }
        }
    }
}

@Composable
fun CodeButton(
    code: String,
    label: String,
    isSelected: Boolean,
    bgActive: Color,
    textActive: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Box(
        modifier = modifier
            .height(44.dp)
            .background(if (isSelected) bgActive else Navy850, RoundedCornerShape(6.dp))
            .border(
                1.dp,
                if (isSelected) textActive else Slate800,
                RoundedCornerShape(6.dp)
            )
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = code,
                fontWeight = FontWeight.ExtraBold,
                fontSize = 14.sp,
                color = if (isSelected) textActive else Slate400
            )
            Text(
                text = label,
                fontSize = 8.sp,
                fontWeight = FontWeight.SemiBold,
                color = if (isSelected) textActive.copy(alpha = 0.85f) else Slate500
            )
        }
    }
}

@Composable
fun FilterPill(
    label: String,
    isSelected: Boolean,
    activeColor: Color = Blue500,
    onClick: () -> Unit
) {
    Box(
        modifier = Modifier
            .background(if (isSelected) Navy800 else Color.Transparent, RoundedCornerShape(4.dp))
            .border(1.dp, if (isSelected) activeColor else Slate800, RoundedCornerShape(4.dp))
            .clickable { onClick() }
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Text(
            text = label,
            fontSize = 11.5.sp,
            fontWeight = FontWeight.Bold,
            color = if (isSelected) activeColor else Slate400
        )
    }
}

@Composable
fun CountBadge(text: String, bg: Color, textCol: Color) {
    Box(
        modifier = Modifier
            .background(bg, RoundedCornerShape(4.dp))
            .padding(horizontal = 5.dp, vertical = 2.dp)
    ) {
        Text(text = text, fontSize = 10.5.sp, fontWeight = FontWeight.Bold, color = textCol)
    }
}
