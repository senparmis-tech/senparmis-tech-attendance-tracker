package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Archive
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.RecordsResponse
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.components.AttendanceCodeBadge
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun RecordsScreen(
    initialSubject: String? = null,
    initialSection: String? = null,
    onNavigateBack: () -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val scope = rememberCoroutineScope()

    var subject by remember { mutableStateOf(initialSubject ?: "") }
    var section by remember { mutableStateOf(initialSection ?: "") }
    var recordsData by remember { mutableStateOf<RecordsResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun loadRecords() {
        if (subject.isBlank()) return
        isLoading = true
        errorMessage = null
        scope.launch {
            val res = repository.getRecords(subject, section.ifBlank { null })
            isLoading = false
            if (res.isSuccess) {
                recordsData = res.getOrNull()
            } else {
                errorMessage = res.exceptionOrNull()?.message ?: "Failed to load records."
            }
        }
    }

    LaunchedEffect(subject, section) {
        if (subject.isNotBlank()) {
            loadRecords()
        } else {
            scope.launch {
                val subsRes = repository.getSubjects()
                if (subsRes.isSuccess && subsRes.getOrNull()?.subjects?.isNotEmpty() == true) {
                    val first = subsRes.getOrNull()!!.subjects.first()
                    subject = first.name
                    section = first.sections.firstOrNull() ?: "BSCS-1A"
                    loadRecords()
                } else {
                    isLoading = false
                }
            }
        }
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Attendance Records",
                subtitle = if (subject.isNotBlank()) "$subject · $section" else "Class Sheet Grid",
                actions = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Slate400)
                    }
                    IconButton(onClick = { loadRecords() }) {
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
            val data = recordsData ?: return@Scaffold
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
                                text = "Archived Subject · Historical records preserved (Read-Only)",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = Slate200
                            )
                        }
                    }
                }

                // Summary stats bar
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(14.dp)
                        .background(Navy900, RoundedCornerShape(8.dp))
                        .border(1.dp, Slate800, RoundedCornerShape(8.dp))
                        .padding(10.dp),
                    horizontalArrangement = Arrangement.SpaceAround
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("${data.rows.size}", fontWeight = FontWeight.Bold, color = Slate50, fontSize = 16.sp)
                        Text("Students", fontSize = 10.sp, color = Slate400)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("${data.dates.size}", fontWeight = FontWeight.Bold, color = Slate50, fontSize = 16.sp)
                        Text("Sessions", fontSize = 10.sp, color = Slate400)
                    }
                    val totalP = data.rows.sumOf { it.p }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("$totalP", fontWeight = FontWeight.Bold, color = PresentGreen, fontSize = 16.sp)
                        Text("Present", fontSize = 10.sp, color = Slate400)
                    }
                    val totalA = data.rows.sumOf { it.x }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("$totalA", fontWeight = FontWeight.Bold, color = AbsentRed, fontSize = 16.sp)
                        Text("Absent", fontSize = 10.sp, color = Slate400)
                    }
                }

                // Student Cards List
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .padding(horizontal = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(bottom = 16.dp)
                ) {
                    items(data.rows) { row ->
                        Card(
                            colors = CardDefaults.cardColors(containerColor = Navy900),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth()
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
                                    if (row.rate != null) {
                                        val pct = (row.rate * 100).toInt()
                                        Box(
                                            modifier = Modifier
                                                .background(
                                                    if (pct < 80) AbsentBg else PresentBg,
                                                    RoundedCornerShape(4.dp)
                                                )
                                                .padding(horizontal = 6.dp, vertical = 2.dp)
                                        ) {
                                            Text(
                                                text = "$pct%",
                                                fontWeight = FontWeight.Bold,
                                                fontSize = 11.sp,
                                                color = if (pct < 80) AbsentRed else PresentGreen
                                            )
                                        }
                                    }
                                }

                                Spacer(modifier = Modifier.height(8.dp))

                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text("P: ${row.p}", fontSize = 11.sp, color = PresentGreen, fontWeight = FontWeight.Bold)
                                    Text("A: ${row.x}", fontSize = 11.sp, color = AbsentRed, fontWeight = FontWeight.Bold)
                                    Text("L: ${row.l}", fontSize = 11.sp, color = LateYellow, fontWeight = FontWeight.Bold)
                                    Text("E: ${row.e}", fontSize = 11.sp, color = ExcusedBlue, fontWeight = FontWeight.Bold)
                                    Text("R: ${row.r}", fontSize = 11.sp, color = RecitedPurple, fontWeight = FontWeight.Bold)
                                }

                                if (row.codes.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .horizontalScroll(rememberScrollState()),
                                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                                    ) {
                                        row.codes.forEachIndexed { idx, code ->
                                            if (code.isNotBlank()) {
                                                AttendanceCodeBadge(code)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
