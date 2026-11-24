package com.senparmitech.attendancetracker.ui.screens

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.GradebookResponse
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

private fun fmt(d: Double): String = if (d % 1.0 == 0.0) d.toInt().toString() else String.format("%.2f", d).trimEnd('0').trimEnd('.')

/** Enter one graded item's scores student by student; each score is saved as you go. */
@Composable
fun ScoreRollCallScreen(
    subject: String,
    section: String,
    itemId: Int,
    onNavigateBack: () -> Unit
) {
    val app = AttendanceApp.instance
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var data by remember { mutableStateOf<GradebookResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val scores = remember { mutableStateMapOf<Int, Double?>() }
    val failed = remember { mutableStateListOf<Int>() }
    var pending by remember { mutableStateOf(0) }
    var idx by remember { mutableStateOf(0) }
    var input by remember { mutableStateOf("") }
    var inputError by remember { mutableStateOf<String?>(null) }

    fun toast(msg: String) = Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()

    val item = data?.items?.firstOrNull { it.id == itemId }
    val rows = data?.rows.orEmpty()
    val max = item?.max_score ?: 0.0

    fun show(i: Int) {
        idx = i.coerceIn(0, rows.size)
        inputError = null
        input = rows.getOrNull(idx)?.let { scores[it.enrollment_id] }?.let(::fmt) ?: ""
    }

    LaunchedEffect(subject, section, itemId) {
        loading = true
        val res = app.repository.getGrades(subject, section.ifBlank { null })
        loading = false
        if (res.isSuccess) {
            val d = res.getOrNull()!!
            data = d
            d.rows.forEach { scores[it.enrollment_id] = it.scores[itemId.toString()] }
            val first = d.rows.indexOfFirst { scores[it.enrollment_id] == null }
            idx = if (first >= 0) first else 0
            input = d.rows.getOrNull(idx)?.let { scores[it.enrollment_id] }?.let(::fmt) ?: ""
        } else error = res.exceptionOrNull()?.message
    }

    fun save(eid: Int, value: Double?) {
        scores[eid] = value
        failed.remove(eid)
        pending++
        scope.launch {
            val err = app.repository.saveScores(subject, section.ifBlank { null }, eid, listOf(itemId to value))
            pending--
            if (err != null) { failed.add(eid); toast(err) }
        }
    }

    /** Reads the box. False when the text is a mistake (the student stays on screen). */
    fun commit(): Boolean {
        val s = rows.getOrNull(idx) ?: return true
        val raw = input.trim().replace(',', '.')
        if (raw.isEmpty()) { inputError = null; return true }
        val v = raw.toDoubleOrNull()
        if (v == null || v < 0) { inputError = "Type a number from 0 to ${fmt(max)}."; return false }
        if (v > max) { inputError = "The highest possible score is ${fmt(max)}."; return false }
        inputError = null
        val rounded = Math.round(v * 100) / 100.0
        if (rounded != scores[s.enrollment_id] || s.enrollment_id in failed) save(s.enrollment_id, rounded)
        return true
    }

    fun next() { if (commit()) show(idx + 1) }
    fun prev() { if (commit()) show(idx - 1) }
    fun quick(v: Double) {
        val s = rows.getOrNull(idx) ?: return
        save(s.enrollment_id, v)
        show(idx + 1)
    }
    fun clear() {
        val s = rows.getOrNull(idx) ?: return
        if (scores[s.enrollment_id] != null) save(s.enrollment_id, null)
        input = ""
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Score roll call",
                subtitle = item?.let { "${it.label}: ${it.title} (out of ${fmt(it.max_score)})" } ?: "$subject · $section",
                actions = {
                    IconButton(onClick = onNavigateBack) { Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Slate400) }
                }
            )
        },
        bottomBar = {
            val scored = scores.values.filterNotNull()
            Surface(color = Navy900, border = androidx.compose.foundation.BorderStroke(1.dp, Slate800), modifier = Modifier.fillMaxWidth()) {
                Row(
                    Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 14.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("${scored.size} / ${rows.size} scored" + if (scored.isNotEmpty()) " · avg ${fmt(scored.average())}" else "",
                        color = Slate300, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        when { failed.isNotEmpty() -> "${failed.size} not saved"; pending > 0 -> "Saving…"; else -> "All saved" },
                        color = if (failed.isNotEmpty()) AbsentRed else PresentGreen, fontSize = 12.sp, fontWeight = FontWeight.Bold
                    )
                }
            }
        },
        containerColor = Navy950
    ) { padding ->
        when {
            loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue500) }
            error != null || item == null -> Box(Modifier.fillMaxSize().padding(padding)) { CenterMessage(error ?: "That graded item was not found.", AbsentRed) }
            rows.isEmpty() -> Box(Modifier.fillMaxSize().padding(padding)) { CenterMessage("There are no students in this section yet.") }
            else -> Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp)) {
                val pct = (idx.toFloat() / rows.size).coerceIn(0f, 1f)
                Panel {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(if (idx >= rows.size) "All ${rows.size} students reviewed" else "Student ${idx + 1} of ${rows.size}",
                            color = Slate200, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        Text("${(pct * 100).toInt()}%", color = Blue400, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                    Spacer(Modifier.height(6.dp))
                    LinearProgressIndicator(progress = { pct }, modifier = Modifier.fillMaxWidth().height(6.dp), color = Blue500, trackColor = Slate800)
                }
                Spacer(Modifier.height(14.dp))

                if (idx >= rows.size) {
                    val blanks = rows.filter { scores[it.enrollment_id] == null }
                    Panel {
                        Text("All scores recorded", color = Slate50, fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
                        Spacer(Modifier.height(8.dp))
                        val vals = scores.values.filterNotNull()
                        Text("Scored ${vals.size} · Blank ${blanks.size}", color = Slate300, fontSize = 13.sp)
                        if (vals.isNotEmpty()) Text(
                            "Average ${fmt(vals.average())} (${fmt(vals.average() / max * 100)}%) · High ${fmt(vals.max())} · Low ${fmt(vals.min())}",
                            color = Slate300, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
                        if (blanks.isNotEmpty()) {
                            Spacer(Modifier.height(10.dp))
                            SmallLabel("STILL BLANK (TAP TO ENTER)")
                            Spacer(Modifier.height(6.dp))
                            ChipRow(blanks.map { it.name }, "") { n -> show(rows.indexOfFirst { it.name == n }) }
                        }
                        Spacer(Modifier.height(12.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = onNavigateBack, colors = ButtonDefaults.buttonColors(containerColor = Blue600)) { Text("Done", fontWeight = FontWeight.Bold) }
                            OutlinedButton(onClick = { show(0) }) { Text("Review from start", color = Slate200) }
                        }
                    }
                } else {
                    val s = rows[idx]
                    Panel {
                        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("STUDENT #${idx + 1}", color = Slate400, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold)
                            Text(s.name, color = Slate50, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold, textAlign = TextAlign.Center,
                                modifier = Modifier.padding(vertical = 8.dp))
                            if (!s.student_no.isNullOrBlank()) Text("ID ${s.student_no}", color = Slate400, fontSize = 12.sp)
                            Spacer(Modifier.height(4.dp))
                            Text(scores[s.enrollment_id]?.let { "Score: ${fmt(it)} / ${fmt(max)}" } ?: "No score yet",
                                color = if (scores[s.enrollment_id] != null) PresentGreen else Slate400, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(14.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                OutlinedTextField(
                                    value = input, onValueChange = { input = it.filter { c -> c.isDigit() || c == '.' || c == ',' }.take(7); inputError = null },
                                    singleLine = true, isError = inputError != null,
                                    textStyle = androidx.compose.ui.text.TextStyle(fontSize = 30.sp, fontWeight = FontWeight.ExtraBold, textAlign = TextAlign.Center),
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Next),
                                    keyboardActions = KeyboardActions(onNext = { next() }),
                                    modifier = Modifier.width(150.dp)
                                )
                                Text("  / ${fmt(max)}", color = Slate400, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                            }
                            Text(inputError ?: " ", color = AbsentRed, fontSize = 12.sp, modifier = Modifier.padding(vertical = 4.dp))
                            Button(
                                onClick = { next() }, shape = androidx.compose.foundation.shape.RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = Blue600), modifier = Modifier.fillMaxWidth().height(50.dp)
                            ) { Text("Save & next student ›", fontWeight = FontWeight.Bold, fontSize = 15.sp) }
                            Spacer(Modifier.height(10.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                                OutlinedButton(onClick = { quick(max) }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("Perfect (${fmt(max)})", fontSize = 11.5.sp, color = Slate200) }
                                OutlinedButton(onClick = { quick(0.0) }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("Zero (0)", fontSize = 11.5.sp, color = Slate200) }
                                OutlinedButton(onClick = { clear() }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("Clear", fontSize = 11.5.sp, color = Slate200) }
                            }
                            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                                TextButton(enabled = idx > 0, onClick = { prev() }) { Text("‹ Previous", fontSize = 12.sp) }
                                TextButton(onClick = { next() }) { Text("Skip ›", fontSize = 12.sp) }
                            }
                        }
                    }
                    if (failed.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        TextButton(onClick = {
                            failed.toList().forEach { eid -> save(eid, scores[eid]) }
                        }) { Text("Retry ${failed.size} unsaved score(s)", color = AbsentRed) }
                    }
                }
            }
        }
    }
}
