package com.senparmitech.attendancetracker.ui.screens

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.GradeItem
import com.senparmitech.attendancetracker.data.api.models.GradebookResponse
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

private fun num(d: Double): String = if (d % 1.0 == 0.0) d.toInt().toString() else d.toString()

/** Category weights, the weight lock, and adding or deleting exams, quizzes and activities. */
@Composable
fun GradeSetupScreen(
    subject: String,
    section: String,
    onNavigateBack: () -> Unit,
    onRollCall: (itemId: Int) -> Unit
) {
    val app = AttendanceApp.instance
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var data by remember { mutableStateOf<GradebookResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<GradeItem?>(null) }

    var exam by remember { mutableStateOf("") }
    var quiz by remember { mutableStateOf("") }
    var activity by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("Exam") }
    var title by remember { mutableStateOf("") }
    var maxScore by remember { mutableStateOf("100") }
    var itemDate by remember { mutableStateOf("") }

    fun toast(msg: String) = Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()

    fun load() {
        loading = true
        error = null
        scope.launch {
            val res = app.repository.getGrades(subject, section.ifBlank { null })
            loading = false
            if (res.isSuccess) {
                val d = res.getOrNull()!!
                data = d
                exam = num(d.weights.exam); quiz = num(d.weights.quiz); activity = num(d.weights.activity)
            } else error = res.exceptionOrNull()?.message
        }
    }

    fun act(path: String, done: String, vararg f: Pair<String, Any?>, after: () -> Unit = {}) {
        busy = true
        scope.launch {
            val err = app.manage.act(path, *f)
            busy = false
            if (err == null) { toast(done); after(); load() } else toast(err)
        }
    }

    LaunchedEffect(subject, section) { load() }

    deleteTarget?.let { item ->
        ConfirmDialog(
            title = "Delete ${item.title}?", confirm = "Delete", busy = busy,
            text = "This also deletes every score entered for it.",
            onDismiss = { deleteTarget = null }
        ) {
            act("/api/grade_item_delete", "Deleted.", "subject" to subject, "section" to section, "item_id" to item.id) { deleteTarget = null }
        }
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Grade setup",
                subtitle = "$subject · $section",
                actions = {
                    IconButton(onClick = onNavigateBack) { Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Slate400) }
                }
            )
        },
        containerColor = Navy950
    ) { padding ->
        val d = data
        when {
            loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue500) }
            error != null || d == null -> Box(Modifier.fillMaxSize().padding(padding)) { CenterMessage(error ?: "Could not load.", AbsentRed) { load() } }
            else -> {
                val readOnly = d.is_archived
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp),
                    contentPadding = PaddingValues(vertical = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    if (readOnly) item { Tag("Archived subject: read-only") }

                    item {
                        Panel {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                Text("Category weights", color = Slate50, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                if (!readOnly) TextButton(enabled = !busy, onClick = {
                                    act("/api/grade_lock", if (d.locked) "Weights unlocked." else "Weights locked.",
                                        "subject" to subject, "section" to section, "locked" to !d.locked)
                                }) { Text(if (d.locked) "Locked: tap to unlock" else "Unlocked: tap to lock", fontSize = 12.sp) }
                            }
                            Text("Weights must add up to 100%.", color = Slate400, fontSize = 12.sp)
                            Spacer(Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                listOf(Triple("Exam %", exam, { v: String -> exam = v }),
                                    Triple("Quiz %", quiz, { v: String -> quiz = v }),
                                    Triple("Activity %", activity, { v: String -> activity = v })).forEach { (label, value, set) ->
                                    OutlinedTextField(
                                        value = value, onValueChange = { set(it.filter { c -> c.isDigit() || c == '.' }.take(6)) },
                                        label = { Text(label) }, singleLine = true, enabled = !d.locked && !readOnly,
                                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                            if (!d.locked && !readOnly) {
                                Spacer(Modifier.height(8.dp))
                                Button(
                                    enabled = !busy,
                                    onClick = {
                                        act("/api/grade_weights", "Weights saved.", "subject" to subject, "section" to section,
                                            "exam" to exam, "quiz" to quiz, "activity" to activity)
                                    },
                                    colors = ButtonDefaults.buttonColors(containerColor = Blue600)
                                ) { Text("Save weights", fontWeight = FontWeight.Bold) }
                            }
                        }
                    }

                    if (!readOnly) item {
                        Panel {
                            Text("Add exam, quiz or activity", color = Slate50, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            Spacer(Modifier.height(8.dp))
                            ChipRow(listOf("Exam", "Quiz", "Activity"), category) { category = it }
                            OutlinedTextField(
                                value = title, onValueChange = { title = it }, label = { Text("Title (e.g. Midterm Exam, Quiz 1)") },
                                singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                                OutlinedTextField(
                                    value = maxScore, onValueChange = { maxScore = it.filter { c -> c.isDigit() || c == '.' }.take(7) },
                                    label = { Text("Max points") }, singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f)
                                )
                                OutlinedTextField(
                                    value = itemDate, onValueChange = { itemDate = it }, label = { Text("Date (YYYY-MM-DD)") },
                                    singleLine = true, modifier = Modifier.weight(1.2f)
                                )
                            }
                            Spacer(Modifier.height(8.dp))
                            Button(
                                enabled = !busy && title.isNotBlank(),
                                onClick = {
                                    act("/api/grade_item_add", "Added.", "subject" to subject, "section" to section,
                                        "category" to category.lowercase(), "title" to title, "max_score" to maxScore, "date" to itemDate) {
                                        title = ""; itemDate = ""
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Blue600)
                            ) { Text("Add item", fontWeight = FontWeight.Bold) }
                        }
                    }

                    item { SmallLabel("GRADED ITEMS (${d.items.size})") }
                    if (d.items.isEmpty()) item { Text("Nothing added yet.", color = Slate500, fontSize = 13.sp) }
                    items(d.items, key = { it.id }) { item ->
                        Panel {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(item.title, color = Slate50, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                    Text("${item.label} · out of ${num(item.max_score)}", color = Slate400, fontSize = 11.5.sp)
                                }
                                if (!readOnly) {
                                    Button(onClick = { onRollCall(item.id) }, colors = ButtonDefaults.buttonColors(containerColor = Blue600),
                                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) { Text("Roll call", fontSize = 12.sp) }
                                    TextButton(onClick = { deleteTarget = item }) { Text("Delete", fontSize = 12.sp, color = AbsentRed) }
                                }
                            }
                        }
                    }
                    item { Spacer(Modifier.height(24.dp)) }
                }
            }
        }
    }
}
