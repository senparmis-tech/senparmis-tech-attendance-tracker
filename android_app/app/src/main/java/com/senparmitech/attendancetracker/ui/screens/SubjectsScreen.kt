package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Archive
import androidx.compose.material.icons.filled.Book
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.GradeOutlined
import androidx.compose.material.icons.filled.ListAlt
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.ArchivedSubjectItem
import com.senparmitech.attendancetracker.data.api.models.SubjectItem
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@Composable
fun SubjectsScreen(
    onNavigateToMark: (subject: String, section: String, dateIso: String) -> Unit,
    onNavigateToRecords: (subject: String, section: String) -> Unit,
    onNavigateToGrades: (subject: String, section: String) -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val scope = rememberCoroutineScope()

    var subjects by remember { mutableStateOf<List<SubjectItem>>(emptyList()) }
    var archivedSubjects by remember { mutableStateOf<List<ArchivedSubjectItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var showArchived by remember { mutableStateOf(false) }

    val todayIso = remember { LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE) }

    fun loadData() {
        isLoading = true
        errorMessage = null
        scope.launch {
            val result = repository.getSubjects()
            isLoading = false
            if (result.isSuccess) {
                val data = result.getOrNull()
                subjects = data?.subjects ?: emptyList()
                archivedSubjects = data?.archived_subjects ?: emptyList()
            } else {
                errorMessage = result.exceptionOrNull()?.message ?: "Failed to load subjects."
            }
        }
    }

    LaunchedEffect(Unit) { loadData() }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Subjects",
                subtitle = "${subjects.size} active · ${archivedSubjects.size} archived",
                actions = {
                    IconButton(onClick = { loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = Slate400)
                    }
                }
            )
        },
        containerColor = Navy950
    ) { padding ->
        if (isLoading) {
            Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = Blue500)
            }
        } else if (errorMessage != null) {
            Box(
                modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(errorMessage!!, color = AbsentRed, fontSize = 14.sp)
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = { loadData() },
                        colors = ButtonDefaults.buttonColors(containerColor = Blue600)
                    ) { Text("Retry") }
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp),
                contentPadding = PaddingValues(vertical = 14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Active subjects header
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Book, contentDescription = null, tint = Slate500, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "ACTIVE SUBJECTS (${subjects.size})",
                            style = MaterialTheme.typography.labelSmall,
                            color = Slate400,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                if (subjects.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(Navy900, RoundedCornerShape(8.dp))
                                .border(1.dp, Slate800, RoundedCornerShape(8.dp))
                                .padding(24.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "No active subjects found.",
                                color = Slate500,
                                fontSize = 13.sp
                            )
                        }
                    }
                }

                // Active subject cards
                items(subjects) { subject ->
                    ActiveSubjectCard(
                        subject = subject,
                        todayIso = todayIso,
                        onMark = { section ->
                            onNavigateToMark(subject.name, section, todayIso)
                        },
                        onRecords = { section ->
                            onNavigateToRecords(subject.name, section)
                        },
                        onGrades = { section ->
                            onNavigateToGrades(subject.name, section)
                        }
                    )
                }

                // Archived subjects toggle header
                if (archivedSubjects.isNotEmpty()) {
                    item {
                        Card(
                            onClick = { showArchived = !showArchived },
                            colors = CardDefaults.cardColors(containerColor = Navy900),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Archive, contentDescription = null, tint = Slate500, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column {
                                        Text(
                                            text = "ARCHIVED SUBJECTS",
                                            fontWeight = FontWeight.Bold,
                                            color = Slate300,
                                            fontSize = 13.sp
                                        )
                                        Text(
                                            text = "${archivedSubjects.size} subjects · Records preserved",
                                            fontSize = 11.sp,
                                            color = Slate500
                                        )
                                    }
                                }
                                Icon(
                                    if (showArchived) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                    contentDescription = null,
                                    tint = Slate500,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    }

                    if (showArchived) {
                        items(archivedSubjects) { archived ->
                            ArchivedSubjectCard(
                                archived = archived,
                                onRecords = { onNavigateToRecords(archived.name, "") },
                                onGrades = { onNavigateToGrades(archived.name, "") }
                            )
                        }
                    }
                }

                item { Spacer(modifier = Modifier.height(80.dp)) }
            }
        }
    }
}

@Composable
private fun ActiveSubjectCard(
    subject: SubjectItem,
    todayIso: String,
    onMark: (section: String) -> Unit,
    onRecords: (section: String) -> Unit,
    onGrades: (section: String) -> Unit
) {
    var expanded by remember { mutableStateOf(subject.sections.size == 1) }

    Card(
        colors = CardDefaults.cardColors(containerColor = Navy900),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            // Subject name + section count
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = subject.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate50
                    )
                    Text(
                        text = "${subject.sections.size} section(s) · ${subject.n_students} students",
                        fontSize = 11.sp,
                        color = Slate400,
                        modifier = Modifier.padding(top = 2.dp)
                    )
                }
                if (subject.sections.size > 1) {
                    IconButton(
                        onClick = { expanded = !expanded },
                        modifier = Modifier.size(32.dp)
                    ) {
                        Icon(
                            if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                            contentDescription = null,
                            tint = Slate400,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
            }

            // Section list
            if (expanded || subject.sections.size == 1) {
                Spacer(modifier = Modifier.height(10.dp))
                subject.sections.forEach { section ->
                    SectionRow(
                        section = section,
                        onMark = { onMark(section) },
                        onRecords = { onRecords(section) },
                        onGrades = { onGrades(section) }
                    )
                    if (section != subject.sections.last()) {
                        Divider(color = Slate800, thickness = 0.5.dp, modifier = Modifier.padding(vertical = 6.dp))
                    }
                }
            } else if (subject.sections.size > 1) {
                // Show condensed section pills when collapsed
                Spacer(modifier = Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    subject.sections.take(5).forEach { section ->
                        Box(
                            modifier = Modifier
                                .background(Navy800, RoundedCornerShape(4.dp))
                                .border(1.dp, Slate700, RoundedCornerShape(4.dp))
                                .padding(horizontal = 8.dp, vertical = 3.dp)
                        ) {
                            Text(text = section, fontSize = 11.sp, color = Blue400, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    if (subject.sections.size > 5) {
                        Box(
                            modifier = Modifier
                                .background(Navy800, RoundedCornerShape(4.dp))
                                .padding(horizontal = 8.dp, vertical = 3.dp)
                        ) {
                            Text("+${subject.sections.size - 5} more", fontSize = 11.sp, color = Slate500)
                        }
                    }
                }
                Spacer(modifier = Modifier.height(2.dp))
                TextButton(onClick = { expanded = true }) {
                    Text("Tap to expand sections", fontSize = 11.sp, color = Blue400)
                }
            }
        }
    }
}

@Composable
private fun SectionRow(
    section: String,
    onMark: () -> Unit,
    onRecords: () -> Unit,
    onGrades: () -> Unit
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Box(
                modifier = Modifier
                    .background(Navy800, RoundedCornerShape(4.dp))
                    .border(1.dp, Slate700, RoundedCornerShape(4.dp))
                    .padding(horizontal = 8.dp, vertical = 3.dp)
            ) {
                Text(text = section, fontSize = 12.sp, color = Blue400, fontWeight = FontWeight.ExtraBold)
            }
        }
        Spacer(modifier = Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = onMark,
                shape = RoundedCornerShape(6.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Blue600),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
                modifier = Modifier.weight(1.4f)
            ) {
                Text("Roll Call", fontWeight = FontWeight.Bold, fontSize = 12.sp)
            }
            OutlinedButton(
                onClick = onRecords,
                shape = RoundedCornerShape(6.dp),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
                modifier = Modifier.weight(1f)
            ) {
                Icon(Icons.Default.ListAlt, contentDescription = null, modifier = Modifier.size(14.dp), tint = Slate400)
                Spacer(modifier = Modifier.width(4.dp))
                Text("Records", fontSize = 12.sp, color = Slate200)
            }
            OutlinedButton(
                onClick = onGrades,
                shape = RoundedCornerShape(6.dp),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
                modifier = Modifier.weight(1f)
            ) {
                Icon(Icons.Default.GradeOutlined, contentDescription = null, modifier = Modifier.size(14.dp), tint = Slate400)
                Spacer(modifier = Modifier.width(4.dp))
                Text("Grades", fontSize = 12.sp, color = Slate200)
            }
        }
    }
}

@Composable
private fun ArchivedSubjectCard(
    archived: ArchivedSubjectItem,
    onRecords: () -> Unit,
    onGrades: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Navy850),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = archived.name,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.SemiBold,
                        color = Slate300
                    )
                    if (archived.archived_at != null) {
                        Text(
                            text = "Archived ${archived.archived_at.take(10)}",
                            fontSize = 10.sp,
                            color = Slate500
                        )
                    }
                    if (!archived.archive_note.isNullOrBlank()) {
                        Text(
                            text = archived.archive_note,
                            fontSize = 11.sp,
                            color = Slate400,
                            modifier = Modifier.padding(top = 2.dp)
                        )
                    }
                }
                Box(
                    modifier = Modifier
                        .background(Navy700, RoundedCornerShape(4.dp))
                        .border(1.dp, Slate700, RoundedCornerShape(4.dp))
                        .padding(horizontal = 8.dp, vertical = 3.dp)
                ) {
                    Text("ARCHIVED", fontSize = 9.sp, color = Slate500, fontWeight = FontWeight.ExtraBold)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = onRecords,
                    shape = RoundedCornerShape(6.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Records", fontSize = 12.sp, color = Slate300)
                }
                OutlinedButton(
                    onClick = onGrades,
                    shape = RoundedCornerShape(6.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Gradebook", fontSize = 12.sp, color = Slate300)
                }
            }
        }
    }
}

// Missing colour alias used in this file
private val Slate300 = androidx.compose.ui.graphics.Color(0xFFCBD5E1)
