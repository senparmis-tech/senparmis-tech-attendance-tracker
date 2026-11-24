package com.senparmitech.attendancetracker.ui.screens

import android.widget.Toast
import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.MarkSubmissionItem
import com.senparmitech.attendancetracker.data.api.models.StudentRosterItem
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

enum class AttendanceMode {
    LIST,
    ROLL_CALL
}

@Composable
fun MarkAttendanceScreen(
    initialSubject: String? = null,
    initialSection: String? = null,
    initialDate: String? = null,
    onNavigateBack: () -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val context = LocalContext.current
    val haptic = LocalHapticFeedback.current
    val scope = rememberCoroutineScope()

    var subject by remember { mutableStateOf(initialSubject ?: "") }
    var section by remember { mutableStateOf(initialSection ?: "") }
    var dateIso by remember { mutableStateOf(initialDate ?: LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE)) }
    var dateLabel by remember { mutableStateOf("") }
    var topic by remember { mutableStateOf("") }
    var students by remember { mutableStateOf<List<StudentRosterItem>>(emptyList()) }
    var searchQuery by remember { mutableStateOf("") }
    var filterCode by remember { mutableStateOf<String?>(null) } // null = All, "unmarked", "p", "x", etc.

    var mode by remember { mutableStateOf(AttendanceMode.LIST) }
    var rollIndex by remember { mutableStateOf(0) }
    var isRollCallDone by remember { mutableStateOf(false) }

    var isLoading by remember { mutableStateOf(true) }
    var isSaving by remember { mutableStateOf(false) }
    var hasUnsavedChanges by remember { mutableStateOf(false) }

    val todayIso = remember { LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE) }

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
                rollIndex = 0
                isRollCallDone = false
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
            scope.launch {
                val subResult = repository.getSubjects()
                if (subResult.isSuccess && subResult.getOrNull()?.subjects?.isNotEmpty() == true) {
                    val firstSub = subResult.getOrNull()!!.subjects.first()
                    subject = firstSub.name
                    section = firstSub.sections.firstOrNull() ?: ""
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
        scope.launch {
            val marks = students.map { MarkSubmissionItem(it.row, it.name, it.code) }
            repository.saveDraftLocally(subject, section, dateIso, topic, marks)
        }
    }

    fun markAllPresent() {
        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
        students = students.map { it.copy(code = "p") }
        hasUnsavedChanges = true
        scope.launch {
            val marks = students.map { MarkSubmissionItem(it.row, it.name, it.code) }
            repository.saveDraftLocally(subject, section, dateIso, topic, marks)
        }
    }

    fun resetAllMarks() {
        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
        students = students.map { it.copy(code = "") }
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

    fun changeDay(offset: Long) {
        try {
            val cur = LocalDate.parse(dateIso)
            val next = cur.plusDays(offset)
            dateIso = next.format(DateTimeFormatter.ISO_LOCAL_DATE)
        } catch (e: Exception) {
            // fallback
        }
    }

    // Counts
    val countP = students.count { it.code.lowercase() == "p" }
    val countX = students.count { it.code.lowercase() == "x" }
    val countL = students.count { it.code.lowercase() == "l" }
    val countE = students.count { it.code.lowercase() == "e" }
    val countR = students.count { it.code.lowercase() == "r" }
    val countUnmarked = students.count { it.code.isBlank() }

    // Filtered list
    val filteredStudents = students.filter { s ->
        val matchesSearch = searchQuery.isBlank() || s.name.contains(searchQuery, ignoreCase = true)
        val matchesCode = when (filterCode) {
            null -> true
            "unmarked" -> s.code.isBlank()
            else -> s.code.lowercase() == filterCode!!.lowercase()
        }
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
            // Sticky Floating Mobile Action Dock
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
                                        .size(8.dp)
                                        .background(if (hasUnsavedChanges) Color(0xFFF59E0B) else Color(0xFF22C55E), CircleShape)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    if (hasUnsavedChanges) "Save Changes" else "Saved",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp
                                )
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
                // Date bar + View Mode Switcher
                Surface(
                    color = Navy900,
                    border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        // Date picker navigation
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            IconButton(
                                onClick = { changeDay(-1) },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(Icons.Default.ChevronLeft, contentDescription = "Previous Day", tint = Slate400)
                            }

                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.CalendarToday, contentDescription = null, tint = Blue400, modifier = Modifier.size(14.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = dateLabel.ifBlank { dateIso },
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.5.sp,
                                    color = Slate50
                                )
                                if (dateIso != todayIso) {
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Box(
                                        modifier = Modifier
                                            .background(Blue600.copy(alpha = 0.2f), RoundedCornerShape(4.dp))
                                            .border(1.dp, Blue500, RoundedCornerShape(4.dp))
                                            .clickable { dateIso = todayIso }
                                            .padding(horizontal = 6.dp, vertical = 2.dp)
                                    ) {
                                        Text("Today", fontSize = 10.sp, color = Blue400, fontWeight = FontWeight.Bold)
                                    }
                                }
                            }

                            IconButton(
                                onClick = { changeDay(1) },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(Icons.Default.ChevronRight, contentDescription = "Next Day", tint = Slate400)
                            }
                        }

                        Spacer(modifier = Modifier.height(10.dp))

                        // Segmented Mode Switcher (List vs Roll-Call Mode)
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(Navy950, RoundedCornerShape(8.dp))
                                .border(1.dp, Slate800, RoundedCornerShape(8.dp))
                                .padding(3.dp),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            ModeTabButton(
                                title = "Roster List",
                                icon = Icons.Default.FormatListBulleted,
                                isSelected = mode == AttendanceMode.LIST,
                                modifier = Modifier.weight(1f)
                            ) {
                                mode = AttendanceMode.LIST
                            }
                            ModeTabButton(
                                title = "Roll-Call Mode",
                                icon = Icons.Default.TouchApp,
                                isSelected = mode == AttendanceMode.ROLL_CALL,
                                modifier = Modifier.weight(1f)
                            ) {
                                mode = AttendanceMode.ROLL_CALL
                                if (isRollCallDone && students.isNotEmpty()) {
                                    rollIndex = 0
                                    isRollCallDone = false
                                }
                            }
                        }
                    }
                }

                // Main Content depending on mode
                AnimatedContent(
                    targetState = mode,
                    transitionSpec = { fadeIn(tween(200)) togetherWith fadeOut(tween(200)) },
                    label = "attendance_mode"
                ) { currentMode ->
                    when (currentMode) {
                        AttendanceMode.LIST -> {
                            ListModeView(
                                topic = topic,
                                onTopicChange = { topic = it; hasUnsavedChanges = true },
                                searchQuery = searchQuery,
                                onSearchQueryChange = { searchQuery = it },
                                filterCode = filterCode,
                                onFilterCodeChange = { filterCode = it },
                                countAll = students.size,
                                countUnmarked = countUnmarked,
                                countP = countP,
                                countX = countX,
                                countL = countL,
                                countE = countE,
                                countR = countR,
                                filteredStudents = filteredStudents,
                                onMarkAllPresent = { markAllPresent() },
                                onResetAll = { resetAllMarks() },
                                onCodeSelected = { row, code ->
                                    haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                                    updateStudentCode(row, code)
                                }
                            )
                        }
                        AttendanceMode.ROLL_CALL -> {
                            RollCallModeView(
                                students = students,
                                currentIndex = rollIndex,
                                isDone = isRollCallDone,
                                onSelectCode = { code ->
                                    haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                                    if (rollIndex in students.indices) {
                                        updateStudentCode(students[rollIndex].row, code)
                                        if (rollIndex < students.size - 1) {
                                            rollIndex++
                                        } else {
                                            isRollCallDone = true
                                        }
                                    }
                                },
                                onPrev = {
                                    if (rollIndex > 0) rollIndex--
                                },
                                onSkip = {
                                    if (rollIndex < students.size - 1) {
                                        rollIndex++
                                    } else {
                                        isRollCallDone = true
                                    }
                                },
                                onSwitchToList = { mode = AttendanceMode.LIST },
                                onRestart = {
                                    rollIndex = 0
                                    isRollCallDone = false
                                },
                                onSave = { saveAttendance() },
                                countP = countP,
                                countX = countX,
                                countL = countL,
                                countE = countE,
                                countR = countR
                            )
                        }
                    }
                }
            }
        }
    }
}

// ─── Mode Tab Segmented Button ───────────────────────────────────────────────

@Composable
private fun ModeTabButton(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    isSelected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Box(
        modifier = modifier
            .background(if (isSelected) Blue600 else Color.Transparent, RoundedCornerShape(6.dp))
            .clickable { onClick() }
            .padding(vertical = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                icon,
                contentDescription = null,
                tint = if (isSelected) Slate50 else Slate400,
                modifier = Modifier.size(15.dp)
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = title,
                color = if (isSelected) Slate50 else Slate400,
                fontSize = 12.5.sp,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
            )
        }
    }
}

// ─── List Mode View ──────────────────────────────────────────────────────────

@Composable
private fun ListModeView(
    topic: String,
    onTopicChange: (String) -> Unit,
    searchQuery: String,
    onSearchQueryChange: (String) -> Unit,
    filterCode: String?,
    onFilterCodeChange: (String?) -> Unit,
    countAll: Int,
    countUnmarked: Int,
    countP: Int,
    countX: Int,
    countL: Int,
    countE: Int,
    countR: Int,
    filteredStudents: List<StudentRosterItem>,
    onMarkAllPresent: () -> Unit,
    onResetAll: () -> Unit,
    onCodeSelected: (row: Int, code: String) -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Topic & Fast Actions
        Surface(
            color = Navy900,
            border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "FAST ACTIONS",
                        fontSize = 10.5.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate400
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = onMarkAllPresent,
                            colors = ButtonDefaults.buttonColors(containerColor = Navy800),
                            border = androidx.compose.foundation.BorderStroke(1.dp, PresentGreen.copy(alpha = 0.5f)),
                            shape = RoundedCornerShape(4.dp),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            modifier = Modifier.heightIn(min = 44.dp)
                        ) {
                            Icon(Icons.Default.Check, contentDescription = null, tint = PresentGreen, modifier = Modifier.size(12.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("All Present", fontSize = 11.5.sp, color = PresentGreen, fontWeight = FontWeight.Bold)
                        }
                        OutlinedButton(
                            onClick = onResetAll,
                            shape = RoundedCornerShape(4.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            modifier = Modifier.heightIn(min = 44.dp)
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null, tint = Slate400, modifier = Modifier.size(12.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Reset", fontSize = 11.5.sp, color = Slate400)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                OutlinedTextField(
                    value = topic,
                    onValueChange = onTopicChange,
                    placeholder = { Text("Lesson topic or summary (optional)", fontSize = 12.sp, color = Slate500) },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Blue500,
                        unfocusedBorderColor = Slate800,
                        focusedTextColor = Slate50,
                        unfocusedTextColor = Slate50,
                        focusedContainerColor = Navy850,
                        unfocusedContainerColor = Navy850
                    ),
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }

        // Search Bar
        Box(modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = onSearchQueryChange,
                placeholder = { Text("Search student name...", fontSize = 12.sp, color = Slate500) },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Slate400, modifier = Modifier.size(16.dp)) },
                trailingIcon = if (searchQuery.isNotBlank()) {
                    {
                        IconButton(onClick = { onSearchQueryChange("") }) {
                            Icon(Icons.Default.Close, contentDescription = "Clear", tint = Slate400, modifier = Modifier.size(16.dp))
                        }
                    }
                } else null,
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Blue500,
                    unfocusedBorderColor = Slate800,
                    focusedTextColor = Slate50,
                    unfocusedTextColor = Slate50,
                    focusedContainerColor = Navy900,
                    unfocusedContainerColor = Navy900
                ),
                modifier = Modifier.fillMaxWidth()
            )
        }

        // Filter Pills with Real-Time Counters
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 14.dp, vertical = 2.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            CountFilterPill("All", countAll, filterCode == null, Blue500) { onFilterCodeChange(null) }
            if (countUnmarked > 0) {
                CountFilterPill("Unmarked", countUnmarked, filterCode == "unmarked", Slate500) { onFilterCodeChange("unmarked") }
            }
            CountFilterPill("P", countP, filterCode == "p", PresentGreen) { onFilterCodeChange("p") }
            CountFilterPill("A", countX, filterCode == "x", AbsentRed) { onFilterCodeChange("x") }
            CountFilterPill("L", countL, filterCode == "l", LateYellow) { onFilterCodeChange("l") }
            CountFilterPill("E", countE, filterCode == "e", ExcusedBlue) { onFilterCodeChange("e") }
            CountFilterPill("R", countR, filterCode == "r", RecitedPurple) { onFilterCodeChange("r") }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Student List
        if (filteredStudents.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(32.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = if (searchQuery.isNotBlank()) "No students matching \"$searchQuery\"" else "No students in this filter.",
                    color = Slate500,
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(bottom = 14.dp)
            ) {
                itemsIndexed(filteredStudents, key = { _, it -> it.row }) { idx, s ->
                    StudentMarkRow(
                        index = idx + 1,
                        student = s,
                        onCodeSelected = { code -> onCodeSelected(s.row, code) }
                    )
                }
            }
        }
    }
}

// ─── Roll-Call Flashcard Mode View ───────────────────────────────────────────

@Composable
private fun RollCallModeView(
    students: List<StudentRosterItem>,
    currentIndex: Int,
    isDone: Boolean,
    onSelectCode: (code: String) -> Unit,
    onPrev: () -> Unit,
    onSkip: () -> Unit,
    onSwitchToList: () -> Unit,
    onRestart: () -> Unit,
    onSave: () -> Unit,
    countP: Int,
    countX: Int,
    countL: Int,
    countE: Int,
    countR: Int
) {
    if (students.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No students enrolled in this section.", color = Slate400, fontSize = 14.sp)
        }
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        if (!isDone && currentIndex in students.indices) {
            val student = students[currentIndex]
            val progress = (currentIndex + 1).toFloat() / students.size

            // Progress Header
            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Student ${currentIndex + 1} of ${students.size}",
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            color = Slate200
                        )
                        Text(
                            text = "${(progress * 100).toInt()}%",
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            color = Blue400
                        )
                    }
                    Spacer(modifier = Modifier.height(6.dp))
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.fillMaxWidth().height(6.dp),
                        color = Blue500,
                        trackColor = Slate800,
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Main Student Focus Flashcard
            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Blue500.copy(alpha = 0.3f)),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier
                            .background(Navy800, RoundedCornerShape(6.dp))
                            .border(1.dp, Slate700, RoundedCornerShape(6.dp))
                            .padding(horizontal = 10.dp, vertical = 4.dp)
                    ) {
                        Text(
                            text = "STUDENT #${currentIndex + 1}",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = Slate400
                        )
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = student.name,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        color = Slate50,
                        textAlign = TextAlign.Center
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Current status pill
                    val (statusBg, statusFg, statusText) = when (student.code.lowercase()) {
                        "p" -> Triple(PresentBg, PresentGreen, "Currently: Present")
                        "x" -> Triple(AbsentBg, AbsentRed, "Currently: Absent")
                        "l" -> Triple(LateBg, LateYellow, "Currently: Late")
                        "e" -> Triple(ExcusedBg, ExcusedBlue, "Currently: Excused")
                        "r" -> Triple(RecitedBg, RecitedPurple, "Currently: Recited")
                        else -> Triple(Navy800, Slate400, "Not Marked Yet")
                    }

                    Box(
                        modifier = Modifier
                            .background(statusBg, RoundedCornerShape(4.dp))
                            .padding(horizontal = 8.dp, vertical = 3.dp)
                    ) {
                        Text(
                            text = statusText,
                            fontSize = 11.5.sp,
                            fontWeight = FontWeight.Bold,
                            color = statusFg
                        )
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // 5 Giant Big Buttons for Flashcard Roll-Call
                    RollCallBigButton(
                        code = "✓  P",
                        label = "Present",
                        bgColor = PresentBg,
                        textColor = PresentGreen,
                        isSelected = student.code.lowercase() == "p",
                        onClick = { onSelectCode("p") }
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    RollCallBigButton(
                        code = "✗  A",
                        label = "Absent",
                        bgColor = AbsentBg,
                        textColor = AbsentRed,
                        isSelected = student.code.lowercase() == "x",
                        onClick = { onSelectCode("x") }
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        RollCallMediumButton(
                            code = "⏱ Late",
                            bgColor = LateBg,
                            textColor = LateYellow,
                            isSelected = student.code.lowercase() == "l",
                            modifier = Modifier.weight(1f),
                            onClick = { onSelectCode("l") }
                        )
                        RollCallMediumButton(
                            code = "✉ Excused",
                            bgColor = ExcusedBg,
                            textColor = ExcusedBlue,
                            isSelected = student.code.lowercase() == "e",
                            modifier = Modifier.weight(1f),
                            onClick = { onSelectCode("e") }
                        )
                        RollCallMediumButton(
                            code = "★ Recited",
                            bgColor = RecitedBg,
                            textColor = RecitedPurple,
                            isSelected = student.code.lowercase() == "r",
                            modifier = Modifier.weight(1f),
                            onClick = { onSelectCode("r") }
                        )
                    }

                    Spacer(modifier = Modifier.height(18.dp))

                    // Navigation Controls
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedButton(
                            onClick = onPrev,
                            enabled = currentIndex > 0,
                            shape = RoundedCornerShape(6.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate700)
                        ) {
                            Text("‹ Previous", fontSize = 12.sp, color = if (currentIndex > 0) Slate200 else Slate600)
                        }

                        TextButton(onClick = onSwitchToList) {
                            Text("Switch to List", fontSize = 12.sp, color = Blue400)
                        }

                        OutlinedButton(
                            onClick = onSkip,
                            shape = RoundedCornerShape(6.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate700)
                        ) {
                            Text("Skip ›", fontSize = 12.sp, color = Slate200)
                        }
                    }
                }
            }
        } else {
            // Roll Call Finished Screen
            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, PresentGreen.copy(alpha = 0.5f)),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier
                            .size(64.dp)
                            .background(PresentBg, CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, tint = PresentGreen, modifier = Modifier.size(36.dp))
                    }

                    Spacer(modifier = Modifier.height(14.dp))

                    Text(
                        text = "Roll-Call Complete!",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        color = Slate50
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "All ${students.size} enrolled students have been verified.",
                        fontSize = 13.sp,
                        color = Slate400,
                        textAlign = TextAlign.Center
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Summary Pills
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.padding(vertical = 4.dp)
                    ) {
                        CountBadge("P $countP", PresentBg, PresentGreen)
                        CountBadge("A $countX", AbsentBg, AbsentRed)
                        CountBadge("L $countL", LateBg, LateYellow)
                        CountBadge("E $countE", ExcusedBg, ExcusedBlue)
                        CountBadge("R $countR", RecitedBg, RecitedPurple)
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    Button(
                        onClick = onSave,
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Blue600),
                        modifier = Modifier.fillMaxWidth().height(46.dp)
                    ) {
                        Icon(Icons.Default.Save, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Save Attendance to Server", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        OutlinedButton(
                            onClick = onSwitchToList,
                            shape = RoundedCornerShape(8.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("Review in List", color = Slate200)
                        }
                        OutlinedButton(
                            onClick = onRestart,
                            shape = RoundedCornerShape(8.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("Restart Roll-Call", color = Slate400)
                        }
                    }
                }
            }
        }
    }
}

// ─── Flashcard Big Button ───────────────────────────────────────────────────

@Composable
private fun RollCallBigButton(
    code: String,
    label: String,
    bgColor: Color,
    textColor: Color,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        color = if (isSelected) textColor else bgColor,
        border = androidx.compose.foundation.BorderStroke(2.dp, if (isSelected) Slate50 else textColor),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth().height(52.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center
        ) {
            Text(
                text = code,
                fontSize = 17.sp,
                fontWeight = FontWeight.ExtraBold,
                color = if (isSelected) Slate50 else textColor
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = label,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                color = if (isSelected) Slate50 else textColor
            )
        }
    }
}

@Composable
private fun RollCallMediumButton(
    code: String,
    bgColor: Color,
    textColor: Color,
    isSelected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        color = if (isSelected) textColor else bgColor,
        border = androidx.compose.foundation.BorderStroke(1.5.dp, if (isSelected) Slate50 else textColor),
        shape = RoundedCornerShape(8.dp),
        modifier = modifier.height(44.dp)
    ) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(
                text = code,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                color = if (isSelected) Slate50 else textColor
            )
        }
    }
}

// ─── Student Mark Row (List Mode) ───────────────────────────────────────────

@Composable
fun StudentMarkRow(
    index: Int,
    student: StudentRosterItem,
    onCodeSelected: (String) -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Navy900),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .background(Navy800, RoundedCornerShape(4.dp))
                            .border(1.dp, Slate700, RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text("#$index", fontSize = 10.5.sp, fontWeight = FontWeight.ExtraBold, color = Slate400)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = student.name,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = Slate50
                    )
                }

                // Active status pill
                val (chipBg, chipFg, chipText) = when (student.code.lowercase()) {
                    "p" -> Triple(PresentBg, PresentGreen, "Present")
                    "x" -> Triple(AbsentBg, AbsentRed, "Absent")
                    "l" -> Triple(LateBg, LateYellow, "Late")
                    "e" -> Triple(ExcusedBg, ExcusedBlue, "Excused")
                    "r" -> Triple(RecitedBg, RecitedPurple, "Recited")
                    else -> Triple(Navy800, Slate500, "Unmarked")
                }
                Box(
                    modifier = Modifier
                        .background(chipBg, RoundedCornerShape(4.dp))
                        .padding(horizontal = 6.dp, vertical = 2.dp)
                ) {
                    Text(chipText, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = chipFg)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // 5 Thumb Buttons (P, A, L, E, R)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                CodeButton("P", "Present", student.code.lowercase() == "p", PresentBg, PresentGreen, Modifier.weight(1f)) { onCodeSelected("p") }
                CodeButton("A", "Absent", student.code.lowercase() == "x", AbsentBg, AbsentRed, Modifier.weight(1f)) { onCodeSelected("x") }
                CodeButton("L", "Late", student.code.lowercase() == "l", LateBg, LateYellow, Modifier.weight(1f)) { onCodeSelected("l") }
                CodeButton("E", "Excused", student.code.lowercase() == "e", ExcusedBg, ExcusedBlue, Modifier.weight(1f)) { onCodeSelected("e") }
                CodeButton("R", "Recited", student.code.lowercase() == "r", RecitedBg, RecitedPurple, Modifier.weight(1f)) { onCodeSelected("r") }
            }
        }
    }
}

@Composable
fun CodeButton(
    letter: String,
    label: String,
    isSelected: Boolean,
    bgActive: Color,
    fgActive: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        color = if (isSelected) fgActive else Navy800,
        border = androidx.compose.foundation.BorderStroke(1.dp, if (isSelected) fgActive else Slate700),
        shape = RoundedCornerShape(6.dp),
        modifier = modifier.height(38.dp)
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = letter,
                fontSize = 13.5.sp,
                fontWeight = FontWeight.ExtraBold,
                color = if (isSelected) Slate50 else Slate300
            )
        }
    }
}

@Composable
private fun CountFilterPill(
    label: String,
    count: Int,
    isSelected: Boolean,
    accentColor: Color,
    onClick: () -> Unit
) {
    Box(
        modifier = Modifier
            .background(if (isSelected) Navy800 else Navy950, RoundedCornerShape(16.dp))
            .border(1.dp, if (isSelected) accentColor else Slate800, RoundedCornerShape(16.dp))
            .clickable { onClick() }
            .heightIn(min = 40.dp)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        contentAlignment = Alignment.Center
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = label,
                fontSize = 11.sp,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                color = if (isSelected) Slate50 else Slate400
            )
            Spacer(modifier = Modifier.width(3.dp))
            Text(
                text = "$count",
                fontSize = 10.sp,
                fontWeight = FontWeight.ExtraBold,
                color = if (isSelected) accentColor else Slate500
            )
        }
    }
}

@Composable
private fun CountBadge(text: String, bg: Color, fg: Color) {
    Box(
        modifier = Modifier
            .background(bg, RoundedCornerShape(4.dp))
            .padding(horizontal = 5.dp, vertical = 2.dp)
    ) {
        Text(text = text, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = fg)
    }
}

private val Slate600 = Color(0xFF475569)
