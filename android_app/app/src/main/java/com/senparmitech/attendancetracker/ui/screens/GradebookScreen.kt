package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Archive
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.GradeItem
import com.senparmitech.attendancetracker.data.api.models.GradebookResponse
import com.senparmitech.attendancetracker.data.api.models.GradebookStudentRow
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun GradebookScreen(
    initialSubject: String? = null,
    initialSection: String? = null,
    onNavigateBack: () -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val scope = rememberCoroutineScope()

    var subject by remember { mutableStateOf(initialSubject ?: "") }
    var section by remember { mutableStateOf(initialSection ?: "") }
    var gradebookData by remember { mutableStateOf<GradebookResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun loadGrades() {
        if (subject.isBlank()) return
        isLoading = true
        errorMessage = null
        scope.launch {
            val res = repository.getGrades(subject, section.ifBlank { null })
            isLoading = false
            if (res.isSuccess) {
                gradebookData = res.getOrNull()
            } else {
                errorMessage = res.exceptionOrNull()?.message ?: "Failed to load gradebook."
            }
        }
    }

    LaunchedEffect(subject, section) {
        if (subject.isNotBlank()) {
            loadGrades()
        } else {
            scope.launch {
                val subsRes = repository.getSubjects()
                if (subsRes.isSuccess && subsRes.getOrNull()?.subjects?.isNotEmpty() == true) {
                    val first = subsRes.getOrNull()!!.subjects.first()
                    subject = first.name
                    section = first.sections.firstOrNull() ?: "BSCS-1A"
                    loadGrades()
                } else {
                    isLoading = false
                }
            }
        }
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Academic Gradebook",
                subtitle = if (subject.isNotBlank()) "$subject · $section" else "Philippine Scale (1.00 – 5.00)",
                actions = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Slate400)
                    }
                    IconButton(onClick = { loadGrades() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = Slate400)
                    }
                }
            )
        },
        containerColor = Navy950
    ) { padding ->
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Blue500)
            }
        } else if (errorMessage != null) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(text = errorMessage!!, color = AbsentRed)
            }
        } else {
            val data = gradebookData ?: return@Scaffold
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
            ) {
                if (data.is_archived) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Navy900)
                            .border(1.dp, Blue600.copy(alpha = 0.5f))
                            .padding(horizontal = 14.dp, vertical = 8.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Archive, contentDescription = null, tint = Blue400, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "Archived Subject · Grade records preserved (Read-Only)",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = Slate200
                            )
                        }
                    }
                }

                // Weights header strip
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 8.dp)
                        .background(Navy900, RoundedCornerShape(6.dp))
                        .border(1.dp, Slate800, RoundedCornerShape(6.dp))
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Weights: Exam ${data.weights.exam.toInt()}% · Quiz ${data.weights.quiz.toInt()}% · Activity ${data.weights.activity.toInt()}%",
                        fontSize = 11.5.sp,
                        color = Slate400,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        text = "${data.items.size} Graded Items",
                        fontSize = 11.sp,
                        color = Blue400,
                        fontWeight = FontWeight.Bold
                    )
                }

                // Expandable student grade cards
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .padding(horizontal = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(bottom = 16.dp)
                ) {
                    items(data.rows, key = { it.enrollment_id }) { row ->
                        StudentGradeCard(row = row, items = data.items)
                    }
                }
            }
        }
    }
}

@Composable
fun StudentGradeCard(row: GradebookStudentRow, items: List<GradeItem>) {
    var isExpanded by remember { mutableStateOf(false) }

    Card(
        colors = CardDefaults.cardColors(containerColor = Navy900),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable { isExpanded = !isExpanded }
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(row.name, fontWeight = FontWeight.Bold, color = Slate50, fontSize = 14.sp)
                    if (!row.student_no.isNullOrBlank()) {
                        Text(row.student_no, fontSize = 11.sp, color = Slate400)
                    }
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (row.final_pct != null) {
                        Box(
                            modifier = Modifier
                                .background(
                                    if (row.passing == false) AbsentBg else PresentBg,
                                    RoundedCornerShape(4.dp)
                                )
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text(
                                text = "%.1f%%".format(row.final_pct),
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp,
                                color = if (row.passing == false) AbsentRed else PresentGreen
                            )
                        }
                    }

                    if (row.scale != null) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = row.scale,
                            fontWeight = FontWeight.ExtraBold,
                            fontSize = 14.sp,
                            color = if (row.passing == false) AbsentRed else PresentGreen
                        )
                    }

                    Icon(
                        imageVector = if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        tint = Slate400,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }

            AnimatedVisibility(visible = isExpanded) {
                Column(modifier = Modifier.padding(top = 12.dp)) {
                    Divider(color = Slate800, thickness = 1.dp)
                    Spacer(modifier = Modifier.height(8.dp))

                    Text("CATEGORY BREAKDOWN", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Slate400)
                    Spacer(modifier = Modifier.height(4.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        val examPct = row.cat_pct["exam"]
                        val quizPct = row.cat_pct["quiz"]
                        val actPct = row.cat_pct["activity"]
                        Text("Exam: ${if (examPct != null) "%.1f%%".format(examPct) else "—"}", fontSize = 11.5.sp, color = Slate200)
                        Text("Quiz: ${if (quizPct != null) "%.1f%%".format(quizPct) else "—"}", fontSize = 11.5.sp, color = Slate200)
                        Text("Activity: ${if (actPct != null) "%.1f%%".format(actPct) else "—"}", fontSize = 11.5.sp, color = Slate200)
                    }

                    if (items.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("ASSESSMENT SCORES", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Slate400)
                        Spacer(modifier = Modifier.height(4.dp))

                        items.forEach { it ->
                            val score = row.scores[it.id.toString()]
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 2.dp),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("${it.label}: ${it.title} (/${it.max_score.toInt()})", fontSize = 11.5.sp, color = Slate400)
                                Text(
                                    text = if (score != null) score.toString() else "—",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Slate50
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
