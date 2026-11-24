package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.PendingActions
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.DashboardCard
import com.senparmitech.attendancetracker.data.api.models.DashboardResponse
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.components.StatMetricCard
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun DashboardScreen(
    onNavigateToMark: (subject: String, section: String, dateIso: String) -> Unit,
    onNavigateToRecords: (subject: String, section: String) -> Unit,
    onNavigateToGrades: (subject: String, section: String) -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val scope = rememberCoroutineScope()

    var dashboardData by remember { mutableStateOf<DashboardResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun loadData() {
        isLoading = true
        errorMessage = null
        scope.launch {
            val result = repository.getDashboard()
            isLoading = false
            if (result.isSuccess) {
                dashboardData = result.getOrNull()
            } else {
                errorMessage = result.exceptionOrNull()?.message ?: "Failed to load dashboard."
            }
        }
    }

    LaunchedEffect(Unit) {
        loadData()
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Academic Dashboard",
                subtitle = dashboardData?.today_label ?: "Eclaro Academy",
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
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = Blue500)
            }
        } else if (errorMessage != null) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(text = errorMessage!!, color = AbsentRed, fontSize = 14.sp)
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(onClick = { loadData() }, colors = ButtonDefaults.buttonColors(containerColor = Blue600)) {
                        Text("Retry")
                    }
                }
            }
        } else {
            val data = dashboardData ?: return@Scaffold
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(horizontal = 14.dp),
                contentPadding = PaddingValues(vertical = 14.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                item {
                    Text(
                        text = "TODAY'S CLASSES",
                        style = MaterialTheme.typography.labelSmall,
                        color = Slate400,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 2.dp)
                    )
                }
                items(data.cards) { card ->
                    SubjectSectionCard(
                        card = card,
                        todayIso = data.today_iso,
                        onMark = { onNavigateToMark(card.subject, card.section, data.today_iso) },
                        onRecords = { onNavigateToRecords(card.subject, card.section) },
                        onGrades = { onNavigateToGrades(card.subject, card.section) }
                    )
                }
                if (data.cards.isEmpty()) {
                    item {
                        Text(
                            "No classes are assigned to your account yet.",
                            color = Slate400,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    }
                }

                // Secondary academic overview follows the daily actions.
                item {
                    Text(
                        text = "ACADEMIC OVERVIEW",
                        style = MaterialTheme.typography.labelSmall,
                        color = Slate400,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 6.dp)
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            StatMetricCard(
                                label = "Total Students",
                                value = data.overview.total_students.toString(),
                                subText = "Active enrollments",
                                modifier = Modifier.weight(1f)
                            )
                            StatMetricCard(
                                label = "Total Subjects",
                                value = data.overview.total_subjects.toString(),
                                subText = "Curriculum courses",
                                modifier = Modifier.weight(1f)
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            StatMetricCard(
                                label = "Class Sections",
                                value = data.overview.total_sections.toString(),
                                subText = "Monitored sections",
                                modifier = Modifier.weight(1f)
                            )
                            StatMetricCard(
                                label = "Completed",
                                value = data.overview.completed_sessions.toString(),
                                subText = "Recorded sessions",
                                modifier = Modifier.weight(1f)
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            StatMetricCard(
                                label = "Pending Today",
                                value = data.overview.pending_rollcalls.toString(),
                                subText = if (data.overview.pending_rollcalls > 0) "Roll calls needed" else "All sections done",
                                accentColor = if (data.overview.pending_rollcalls > 0) LateYellow else PresentGreen,
                                modifier = Modifier.weight(1f)
                            )
                            StatMetricCard(
                                label = "Below 80%",
                                value = data.overview.low_attendance_count.toString(),
                                subText = "Needing intervention",
                                accentColor = if (data.overview.low_attendance_count > 0) AbsentRed else Slate500,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                }

            }
        }
    }
}

@Composable
fun SubjectSectionCard(
    card: DashboardCard,
    todayIso: String,
    onMark: () -> Unit,
    onRecords: () -> Unit,
    onGrades: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Navy900),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = card.subject,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate50
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Box(
                        modifier = Modifier
                            .background(Navy800, RoundedCornerShape(4.dp))
                            .border(1.dp, Slate700, RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = card.section,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = Blue400
                        )
                    }
                }

                if (card.today_recorded) {
                    Box(
                        modifier = Modifier
                            .background(PresentBg, RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.CheckCircle, contentDescription = null, tint = PresentGreen, modifier = Modifier.size(12.dp))
                            Spacer(modifier = Modifier.width(3.dp))
                            Text("Recorded", fontSize = 10.5.sp, fontWeight = FontWeight.Bold, color = PresentGreen)
                        }
                    }
                } else {
                    Box(
                        modifier = Modifier
                            .background(LateBg, RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.PendingActions, contentDescription = null, tint = LateYellow, modifier = Modifier.size(12.dp))
                            Spacer(modifier = Modifier.width(3.dp))
                            Text("Pending", fontSize = 10.5.sp, fontWeight = FontWeight.Bold, color = LateYellow)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "${card.n_students} students enrolled · ${card.held} dates held" +
                        if (card.avg != null) " · avg ${(card.avg * 100).toInt()}%" else "",
                style = MaterialTheme.typography.bodyMedium,
                color = Slate400,
                fontSize = 12.sp
            )

            if (card.today_recorded && card.today_counts != null) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    CountPill("P ${card.today_counts.p}", PresentBg, PresentGreen)
                    CountPill("A ${card.today_counts.x}", AbsentBg, AbsentRed)
                    CountPill("L ${card.today_counts.l}", LateBg, LateYellow)
                    CountPill("E ${card.today_counts.e}", ExcusedBg, ExcusedBlue)
                    CountPill("R ${card.today_counts.r}", RecitedBg, RecitedPurple)
                }
            }

            if (card.today_recorded && card.absent_today.isNotEmpty()) {
                Spacer(modifier = Modifier.height(6.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Absent Today: ", fontSize = 11.sp, color = Slate400, fontWeight = FontWeight.SemiBold)
                    Spacer(modifier = Modifier.width(4.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        card.absent_today.take(3).forEach { name ->
                            Box(
                                modifier = Modifier
                                    .background(AbsentBg, RoundedCornerShape(4.dp))
                                    .padding(horizontal = 6.dp, vertical = 2.dp)
                            ) {
                                Text(name, fontSize = 10.sp, color = AbsentRed, fontWeight = FontWeight.Bold)
                            }
                        }
                        if (card.absent_today.size > 3) {
                            Text("+${card.absent_today.size - 3} more", fontSize = 10.sp, color = Slate500)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onMark,
                    shape = RoundedCornerShape(6.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = if (card.today_recorded) Navy800 else Blue600),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp)
                ) {
                    Text(
                        text = if (card.today_recorded) "Update attendance" else "Take attendance",
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = onRecords,
                        shape = RoundedCornerShape(6.dp),
                        border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                        modifier = Modifier.weight(1f).heightIn(min = 44.dp)
                    ) {
                        Text("Records", fontSize = 13.sp, color = Slate200, maxLines = 1)
                    }
                    OutlinedButton(
                        onClick = onGrades,
                        shape = RoundedCornerShape(6.dp),
                        border = androidx.compose.foundation.BorderStroke(1.dp, Slate700),
                        modifier = Modifier.weight(1f).heightIn(min = 44.dp)
                    ) {
                        Text("Grades", fontSize = 13.sp, color = Slate200, maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
fun CountPill(text: String, bg: androidx.compose.ui.graphics.Color, textCol: androidx.compose.ui.graphics.Color) {
    Box(
        modifier = Modifier
            .background(bg, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(text = text, fontSize = 10.5.sp, fontWeight = FontWeight.Bold, color = textCol)
    }
}
