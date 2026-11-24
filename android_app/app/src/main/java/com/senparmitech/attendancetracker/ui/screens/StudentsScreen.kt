package com.senparmitech.attendancetracker.ui.screens

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.StudentRow
import com.senparmitech.attendancetracker.data.api.models.StudentsResponse
import com.senparmitech.attendancetracker.data.api.models.SubjectItem
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

private enum class StuDialog { ADD, SUBJECT, SECTION_ADD, SECTION_RENAME, SECTION_DELETE, EDIT, REMOVE, DELETE_SUBJECT }

@Composable
fun StudentsScreen() {
    val app = AttendanceApp.instance
    val repo = app.repository
    val manage = app.manage
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val isMonitor = app.sessionManager.isMonitor()

    var subjects by remember { mutableStateOf<List<SubjectItem>>(emptyList()) }
    var subject by remember { mutableStateOf("") }
    var section by remember { mutableStateOf("") }
    var data by remember { mutableStateOf<StudentsResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var query by remember { mutableStateOf("") }
    var dialog by remember { mutableStateOf<StuDialog?>(null) }
    var target by remember { mutableStateOf<StudentRow?>(null) }
    var busy by remember { mutableStateOf(false) }
    var formError by remember { mutableStateOf<String?>(null) }

    fun toast(msg: String) = Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()

    fun loadStudents() {
        if (subject.isBlank()) { loading = false; return }
        loading = true
        error = null
        scope.launch {
            val res = manage.students(subject, section.ifBlank { null })
            loading = false
            if (res.isSuccess) {
                data = res.getOrNull()
                section = data?.section ?: section
            } else error = res.exceptionOrNull()?.message
        }
    }

    fun loadSubjects(keep: Boolean = true) {
        scope.launch {
            val res = repo.getSubjects()
            if (res.isSuccess) {
                subjects = res.getOrNull()?.subjects.orEmpty()
                if (!keep || subject.isBlank() || subjects.none { it.name == subject }) {
                    subject = subjects.firstOrNull()?.name ?: ""
                    section = subjects.firstOrNull()?.sections?.firstOrNull() ?: ""
                }
                loadStudents()
            } else { loading = false; error = res.exceptionOrNull()?.message }
        }
    }

    LaunchedEffect(Unit) { loadSubjects() }

    fun close() { dialog = null; target = null; formError = null; busy = false }

    /** Run a change; on success close the dialog, show [done] and reload. */
    fun run(path: String, done: String, reloadSubjects: Boolean = false, onOk: () -> Unit = {}, f: Array<Pair<String, Any?>>) {
        busy = true
        formError = null
        scope.launch {
            val err = manage.act(path, *f)
            busy = false
            if (err == null) {
                close(); toast(done); onOk()
                if (reloadSubjects) loadSubjects() else loadStudents()
            } else formError = err
        }
    }

    val canEditStructure = !isMonitor
    val rows = data?.rows.orEmpty().filter { query.isBlank() || it.name.contains(query, true) || (it.student_no ?: "").contains(query, true) }

    when (dialog) {
        StuDialog.ADD -> FormDialog(
            title = "Add students", labels = listOf("Names, one per line"), multiline = setOf(0),
            confirm = "Add", busy = busy, error = formError,
            note = "Adding to $subject${if (section.isNotBlank()) " ($section)" else ""}.",
            onDismiss = { close() }
        ) { v -> run("/api/students_add", "Students added.", f = arrayOf("subject" to subject, "section" to section, "names" to v[0].lines())) }

        StuDialog.SUBJECT -> FormDialog(
            title = "New subject", labels = listOf("Subject name", "First section (default BSCS-1A)", "Copy students from (subject name, optional)"),
            confirm = "Create", busy = busy, error = formError, onDismiss = { close() }
        ) { v ->
            run("/api/subject_add", "Subject created.", reloadSubjects = true,
                onOk = { subject = v[0].trim(); section = v[1].trim() },
                f = arrayOf("name" to v[0], "section_name" to v[1], "copy_from" to v[2]))
        }

        StuDialog.SECTION_ADD -> FormDialog(
            title = "Add section to $subject", labels = listOf("Section name", "Copy students from section (optional)"),
            confirm = "Add", busy = busy, error = formError, onDismiss = { close() }
        ) { v ->
            run("/api/section_add", "Section added.", reloadSubjects = true, onOk = { section = v[0].trim() },
                f = arrayOf("subject" to subject, "section" to v[0], "copy_from" to v[1]))
        }

        StuDialog.SECTION_RENAME -> FormDialog(
            title = "Rename section $section", labels = listOf("New name"), initial = listOf(section),
            confirm = "Rename", busy = busy, error = formError, onDismiss = { close() }
        ) { v ->
            run("/api/section_rename", "Section renamed.", reloadSubjects = true, onOk = { section = v[0].trim() },
                f = arrayOf("subject" to subject, "old_section" to section, "new_section" to v[0]))
        }

        StuDialog.SECTION_DELETE -> ConfirmDialog(
            title = "Delete section $section?", confirm = "Delete", busy = busy,
            text = "All attendance records of this section are removed. A backup is saved first.",
            onDismiss = { close() }
        ) { run("/api/section_delete", "Section deleted.", reloadSubjects = true, f = arrayOf("subject" to subject, "section" to section)) }

        StuDialog.DELETE_SUBJECT -> ConfirmDialog(
            title = "Delete $subject?", confirm = "Delete subject", busy = busy,
            text = "This permanently removes the subject, all its sections and its attendance records. Archive it instead if it is only finished.",
            onDismiss = { close() }
        ) { run("/api/subject_delete", "Subject deleted.", reloadSubjects = true, onOk = { subject = "" }, f = arrayOf("subject" to subject)) }

        StuDialog.EDIT -> target?.let { s ->
            FormDialog(
                title = "Edit ${s.name}",
                labels = listOf("Full name", "Student ID", "Guardian name", "Guardian phone", "Student email", "Address"),
                initial = listOf(s.name, s.student_no ?: "", s.guardian_name ?: "", s.guardian_phone ?: "", s.email ?: "", s.address ?: ""),
                busy = busy, error = formError, onDismiss = { close() }
            ) { v ->
                run("/api/student_profile", "Profile saved.",
                    f = arrayOf("old_name" to s.name, "name" to v[0], "student_no" to v[1], "guardian_name" to v[2],
                        "guardian_phone" to v[3], "email" to v[4], "address" to v[5], "subject" to subject))
            }
        }

        StuDialog.REMOVE -> target?.let { s ->
            AlertDialog(
                onDismissRequest = { if (!busy) close() },
                containerColor = Navy900,
                title = { Text("Remove ${s.name}?", color = Slate50, fontSize = 17.sp) },
                text = {
                    Column {
                        Text("Removing from this section deletes their attendance marks here.", color = Slate300, fontSize = 13.sp)
                        if (formError != null) Text(formError!!, color = AbsentRed, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
                    }
                },
                confirmButton = {
                    Row {
                        TextButton(enabled = !busy, onClick = {
                            run("/api/students_remove", "Removed ${s.name}.",
                                f = arrayOf("subject" to subject, "section" to section, "row" to s.row, "name" to s.name))
                        }) { Text("This section") }
                        if (canEditStructure) TextButton(enabled = !busy, onClick = {
                            run("/api/students_remove", "Removed ${s.name}.",
                                f = arrayOf("subject" to subject, "section" to section, "name" to s.name, "everywhere" to true))
                        }) { Text("Everywhere", color = AbsentRed) }
                    }
                },
                dismissButton = { TextButton(enabled = !busy, onClick = { close() }) { Text("Cancel") } }
            )
        }
        null -> {}
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Students & Subjects",
                subtitle = if (subject.isNotBlank()) "$subject · $section" else "Roster management",
                actions = {
                    IconButton(onClick = { loadSubjects() }) { Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = Slate400) }
                }
            )
        },
        containerColor = Navy950
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp),
            contentPadding = PaddingValues(vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            item {
                SubjectSectionPicker(subjects, subject, section) { s, sec ->
                    subject = s; section = sec; query = ""; loadStudents()
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    Button(
                        onClick = { dialog = StuDialog.ADD }, enabled = subject.isNotBlank() && data?.is_archived != true,
                        colors = ButtonDefaults.buttonColors(containerColor = Blue600), modifier = Modifier.weight(1f)
                    ) { Text("Add students", fontSize = 12.5.sp, fontWeight = FontWeight.Bold) }
                    if (canEditStructure) OutlinedButton(onClick = { dialog = StuDialog.SUBJECT }, modifier = Modifier.weight(1f)) {
                        Text("New subject", fontSize = 12.5.sp, color = Slate200)
                    }
                }
            }
            if (canEditStructure && subject.isNotBlank()) {
                item {
                    Panel {
                        SmallLabel("SECTIONS AND SUBJECT")
                        Spacer(Modifier.height(6.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            TextButton(onClick = { dialog = StuDialog.SECTION_ADD }) { Text("Add section", fontSize = 12.sp) }
                            TextButton(onClick = { dialog = StuDialog.SECTION_RENAME }) { Text("Rename", fontSize = 12.sp) }
                            if ((subjects.firstOrNull { it.name == subject }?.sections?.size ?: 0) > 1)
                                TextButton(onClick = { dialog = StuDialog.SECTION_DELETE }) { Text("Delete", fontSize = 12.sp, color = AbsentRed) }
                        }
                        TextButton(onClick = { dialog = StuDialog.DELETE_SUBJECT }) { Text("Delete subject $subject", fontSize = 12.sp, color = AbsentRed) }
                    }
                }
            }
            if (data?.term != null) {
                item { Tag("Term: ${data?.term}${if (data?.term_locked == true) " (locked)" else ""}") }
            }
            item {
                OutlinedTextField(
                    value = query, onValueChange = { query = it }, singleLine = true,
                    placeholder = { Text("Search by name or student ID", fontSize = 12.sp) },
                    modifier = Modifier.fillMaxWidth()
                )
            }
            when {
                loading -> item { Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue500) } }
                error != null -> item { Text(error!!, color = AbsentRed, fontSize = 13.sp) }
                rows.isEmpty() -> item { Text("No students yet. Use Add students.", color = Slate500, fontSize = 13.sp) }
                else -> items(rows, key = { it.row }) { s ->
                    Panel {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                            Column(Modifier.weight(1f)) {
                                Text(s.name, color = Slate50, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                if (!s.student_no.isNullOrBlank()) Text("ID ${s.student_no}", color = Slate400, fontSize = 11.sp)
                            }
                            s.rate?.let { r ->
                                val pct = (r * 100).toInt()
                                Tag("$pct%", if (pct < 80) AbsentRed else PresentGreen)
                            }
                        }
                        val extra = listOfNotNull(
                            s.guardian_name?.takeIf { it.isNotBlank() }?.let { "Guardian: $it" },
                            s.guardian_phone?.takeIf { it.isNotBlank() }, s.email?.takeIf { it.isNotBlank() }
                        ).joinToString(" · ")
                        if (extra.isNotBlank()) Text(extra, color = Slate400, fontSize = 11.5.sp, modifier = Modifier.padding(top = 4.dp))
                        Row {
                            TextButton(onClick = { target = s; dialog = StuDialog.EDIT }) { Text("Edit profile", fontSize = 12.sp) }
                            TextButton(onClick = { target = s; dialog = StuDialog.REMOVE }) { Text("Remove", fontSize = 12.sp, color = AbsentRed) }
                        }
                    }
                }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}
