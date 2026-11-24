package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.StudentLookupProfile
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun LookupScreen(
    onNavigateBack: () -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val scope = rememberCoroutineScope()

    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<StudentLookupProfile>>(emptyList()) }
    var totalMatches by remember { mutableStateOf(0) }
    var isLoading by remember { mutableStateOf(false) }

    fun doSearch(q: String) {
        isLoading = true
        scope.launch {
            val res = repository.searchStudents(q)
            isLoading = false
            if (res.isSuccess) {
                results = res.getOrNull()?.results ?: emptyList()
                totalMatches = res.getOrNull()?.total_matches ?: 0
            }
        }
    }

    LaunchedEffect(Unit) {
        doSearch("")
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Student Lookup",
                subtitle = "Academic Profile & Contact Records",
                actions = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Slate400)
                    }
                }
            )
        },
        containerColor = Navy950
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Search Input
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(14.dp)
            ) {
                OutlinedTextField(
                    value = query,
                    onValueChange = {
                        query = it
                        doSearch(it)
                    },
                    placeholder = { Text("Search by student name or ID...", fontSize = 13.sp) },
                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Slate400) },
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

            Text(
                text = "FOUND $totalMatches ENROLLED STUDENTS",
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = Slate400,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 4.dp)
            )

            if (isLoading) {
                Box(modifier = Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Blue500)
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .padding(horizontal = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = PaddingValues(bottom = 16.dp)
                ) {
                    items(results) { p ->
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
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(p.name, fontWeight = FontWeight.Bold, color = Slate50, fontSize = 15.sp)
                                        if (!p.student_no.isNullOrBlank()) {
                                            Text("ID: ${p.student_no}", fontSize = 11.5.sp, color = Blue400, fontWeight = FontWeight.SemiBold)
                                        }
                                    }
                                    if (p.sections.isNotEmpty()) {
                                        Box(
                                            modifier = Modifier
                                                .background(Navy800, RoundedCornerShape(4.dp))
                                                .border(1.dp, Slate700, RoundedCornerShape(4.dp))
                                                .padding(horizontal = 6.dp, vertical = 2.dp)
                                        ) {
                                            Text(p.sections.joinToString(", "), fontSize = 11.sp, color = Slate300, fontWeight = FontWeight.Bold)
                                        }
                                    }
                                }

                                if (!p.guardian_name.isNullOrBlank() || !p.guardian_phone.isNullOrBlank()) {
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(Icons.Default.Phone, contentDescription = null, tint = Slate400, modifier = Modifier.size(13.dp))
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = "Guardian: ${p.guardian_name.orEmpty()} (${p.guardian_phone.orEmpty()})",
                                            fontSize = 11.5.sp,
                                            color = Slate400
                                        )
                                    }
                                }

                                if (p.subjects.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(10.dp))
                                    Divider(color = Slate800, thickness = 1.dp)
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Text("ACADEMIC ENROLLMENTS & STANDING", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Slate400)
                                    Spacer(modifier = Modifier.height(4.dp))

                                    p.subjects.forEach { s ->
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(vertical = 2.dp),
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text("${s.subject} (${s.section})", fontSize = 12.sp, color = Slate200)
                                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                                if (s.rate != null) {
                                                    Text(
                                                        "Att: ${(s.rate * 100).toInt()}%",
                                                        fontSize = 11.5.sp,
                                                        fontWeight = FontWeight.Bold,
                                                        color = if (s.rate < 0.8) AbsentRed else PresentGreen
                                                    )
                                                }
                                                if (s.scale != null && s.final_pct != null) {
                                                    Text(
                                                        "%.1f%% (%s)".format(s.final_pct, s.scale),
                                                        fontSize = 11.5.sp,
                                                        fontWeight = FontWeight.Bold,
                                                        color = Blue400
                                                    )
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
}
