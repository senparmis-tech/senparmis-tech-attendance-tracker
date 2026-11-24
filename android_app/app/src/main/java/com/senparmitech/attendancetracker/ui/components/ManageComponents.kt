package com.senparmitech.attendancetracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.data.api.models.SubjectItem
import com.senparmitech.attendancetracker.ui.theme.*

@Composable
fun SmallLabel(text: String, modifier: Modifier = Modifier) {
    Text(text, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Slate400, modifier = modifier)
}

@Composable
fun Panel(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(Navy900, RoundedCornerShape(8.dp))
            .border(1.dp, Slate800, RoundedCornerShape(8.dp))
            .padding(14.dp),
        content = content
    )
}

@Composable
fun Tag(text: String, color: androidx.compose.ui.graphics.Color = Blue400) {
    Box(
        modifier = Modifier
            .background(Navy800, RoundedCornerShape(4.dp))
            .border(1.dp, Slate700, RoundedCornerShape(4.dp))
            .padding(horizontal = 7.dp, vertical = 2.dp)
    ) { Text(text, fontSize = 11.sp, color = color, fontWeight = FontWeight.Bold) }
}

/** A row of tappable choices that scrolls sideways. */
@Composable
fun ChipRow(items: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        items.forEach { item ->
            val on = item.equals(selected, ignoreCase = true)
            Box(
                modifier = Modifier
                    .background(if (on) Blue600 else Navy900, RoundedCornerShape(6.dp))
                    .border(1.dp, if (on) Blue600 else Slate700, RoundedCornerShape(6.dp))
                    .clickable { onSelect(item) }
                    .padding(horizontal = 12.dp, vertical = 7.dp)
            ) {
                Text(item, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = if (on) Slate50 else Slate300)
            }
        }
    }
}

/** Subject tabs with section tabs under them, like the tabs at the top of the website pages. */
@Composable
fun SubjectSectionPicker(
    subjects: List<SubjectItem>,
    subject: String,
    section: String,
    onChange: (subject: String, section: String) -> Unit
) {
    if (subjects.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        ChipRow(subjects.map { it.name }, subject) { name ->
            val sections = subjects.firstOrNull { it.name == name }?.sections.orEmpty()
            onChange(name, sections.firstOrNull() ?: "")
        }
        val sections = subjects.firstOrNull { it.name == subject }?.sections.orEmpty()
        if (sections.size > 1) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SmallLabel("SECTION")
                ChipRow(sections, section) { onChange(subject, it) }
            }
        }
    }
}

@Composable
fun FormDialog(
    title: String,
    labels: List<String>,
    initial: List<String> = labels.map { "" },
    confirm: String = "Save",
    busy: Boolean = false,
    error: String? = null,
    note: String? = null,
    multiline: Set<Int> = emptySet(),
    password: Set<Int> = emptySet(),
    onDismiss: () -> Unit,
    onConfirm: (List<String>) -> Unit
) {
    val values = remember { mutableStateListOf<String>().also { it.addAll(initial) } }
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        containerColor = Navy900,
        title = { Text(title, color = Slate50, fontSize = 17.sp) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                if (note != null) {
                    Text(note, color = Slate300, fontSize = 12.5.sp)
                    Spacer(Modifier.height(6.dp))
                }
                labels.forEachIndexed { i, label ->
                    OutlinedTextField(
                        value = values[i],
                        onValueChange = { values[i] = it },
                        label = { Text(label) },
                        singleLine = i !in multiline,
                        minLines = if (i in multiline) 4 else 1,
                        visualTransformation = if (i in password) PasswordVisualTransformation() else VisualTransformation.None,
                        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                    )
                }
                if (error != null) {
                    Spacer(Modifier.height(6.dp))
                    Text(error, color = AbsentRed, fontSize = 12.sp)
                }
            }
        },
        confirmButton = { TextButton(enabled = !busy, onClick = { onConfirm(values.toList()) }) { Text(confirm) } },
        dismissButton = { TextButton(enabled = !busy, onClick = onDismiss) { Text("Cancel") } }
    )
}

@Composable
fun ConfirmDialog(
    title: String,
    text: String,
    confirm: String,
    busy: Boolean = false,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit
) {
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        containerColor = Navy900,
        title = { Text(title, color = Slate50, fontSize = 17.sp) },
        text = { Text(text, color = Slate300, fontSize = 13.sp) },
        confirmButton = { TextButton(enabled = !busy, onClick = onConfirm) { Text(confirm) } },
        dismissButton = { TextButton(enabled = !busy, onClick = onDismiss) { Text("Cancel") } }
    )
}

@Composable
fun CenterMessage(text: String, color: androidx.compose.ui.graphics.Color = Slate400, onRetry: (() -> Unit)? = null) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(text, color = color, fontSize = 14.sp)
            if (onRetry != null) {
                Spacer(Modifier.height(10.dp))
                Button(onClick = onRetry, colors = ButtonDefaults.buttonColors(containerColor = Blue600)) { Text("Retry") }
            }
        }
    }
}
