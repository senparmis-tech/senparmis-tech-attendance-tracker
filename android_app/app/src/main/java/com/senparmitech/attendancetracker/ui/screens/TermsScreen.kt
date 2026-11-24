package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.*
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable fun TermsScreen(onBack: () -> Unit) {
    val app = AttendanceApp.instance; val scope = rememberCoroutineScope()
    var subjects by remember { mutableStateOf<List<SubjectItem>>(emptyList()) }; var subject by remember { mutableStateOf("") }; var section by remember { mutableStateOf("") }
    var data by remember { mutableStateOf<PeriodsResponse?>(null) }; var loading by remember { mutableStateOf(true) }; var err by remember { mutableStateOf<String?>(null) }; var confirm by remember { mutableStateOf<PeriodItem?>(null) }
    fun load() { if (subject.isBlank()) { loading=false; return }; loading=true; scope.launch { val r=app.manage.periods(subject,section.ifBlank { null }); loading=false; if(r.isSuccess){data=r.getOrNull();err=null}else err=r.exceptionOrNull()?.message } }
    LaunchedEffect(Unit) { val r=app.repository.getSubjects(); if(r.isSuccess){subjects=r.getOrNull()?.subjects.orEmpty(); subject=subjects.firstOrNull()?.name.orEmpty(); section=subjects.firstOrNull()?.sections?.firstOrNull().orEmpty(); load()} else {loading=false;err=r.exceptionOrNull()?.message} }
    fun action(path:String, fields:Map<String,Any?>) { scope.launch { val e=app.manage.act(path,*fields.entries.map { it.key to it.value }.toTypedArray()); if(e==null) load() else err=e } }
    confirm?.let { p -> AlertDialog(onDismissRequest={confirm=null},title={Text("Lock ${p.label}?")},text={Text("This closes the term and opens ${data?.next_semester} ${data?.next_term}.")},confirmButton={TextButton(onClick={confirm=null;action("/api/period_lock",mapOf("subject" to subject,"section" to section,"semester" to p.semester,"term" to p.term,"next_semester" to data?.next_semester,"next_term" to data?.next_term))}){Text("Lock term")} },dismissButton={TextButton(onClick={confirm=null}){Text("Cancel")}}) }
    Scaffold(topBar={AcademicTopBar("Terms",subject.ifBlank { "Manage academic periods" }) { IconButton(onClick=onBack){Icon(Icons.Default.ArrowBack,null,tint=Slate400)} }}) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).padding(16.dp), verticalArrangement=Arrangement.spacedBy(12.dp)) {
            SubjectSectionPicker(subjects,subject,section){s,c->subject=s;section=c;load()}
            if(loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            err?.let { Text(it,color=AbsentRed) }
            data?.let { d ->
                LazyColumn(verticalArrangement=Arrangement.spacedBy(8.dp)) { items(d.periods){p->Panel { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Column(Modifier.weight(1f)){Text(p.label,color=Slate50,fontWeight=FontWeight.Bold);Text("${p.n_dates} attendance dates · ${p.n_items} grade items",color=Slate400);Text(if(p.locked) "Locked ${p.locked_at.orEmpty()}" else "Current term",color=if(p.locked) Slate400 else Blue400)}; if(!p.locked) TextButton(onClick={confirm=p}){Text("Lock")}; if(p.locked&&d.is_admin) TextButton(onClick={action("/api/period_unlock",mapOf("subject" to subject,"section" to section,"period_id" to p.id))}){Text("Reopen")}} } } }
            }
        }
    }
}
