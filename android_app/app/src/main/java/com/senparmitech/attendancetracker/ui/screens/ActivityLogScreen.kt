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
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable fun ActivityLogScreen(onBack:()->Unit) {
    val app=AttendanceApp.instance; val scope= rememberCoroutineScope(); var entries by remember { mutableStateOf(emptyList<com.senparmitech.attendancetracker.data.api.models.LogEntry>()) }; var loading by remember { mutableStateOf(true) }; var error by remember { mutableStateOf<String?>(null) }
    fun load(){loading=true;scope.launch{val r=app.manage.log();loading=false;if(r.isSuccess){entries=r.getOrNull()?.entries.orEmpty();error=null}else error=r.exceptionOrNull()?.message}}
    LaunchedEffect(Unit){load()}
    Scaffold(topBar={AcademicTopBar("Activity log","Recent changes") { IconButton(onClick=onBack){Icon(Icons.Default.ArrowBack,null,tint=Slate400)} }}) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).padding(16.dp)) {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("${entries.size} entries",color=Slate400);TextButton(onClick=::load){Text("Refresh")}}
            if(loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            error?.let{Text(it,color=AbsentRed)}
            LazyColumn(verticalArrangement=Arrangement.spacedBy(8.dp)){items(entries){e->Panel { Text(e.action,color=Slate50,fontWeight=FontWeight.Bold);Text(listOf(e.subject,e.whenText).filter{it.isNotBlank()}.joinToString(" · "),color=Blue400);if(e.detail.isNotBlank())Text(e.detail,color=Slate300);if(e.who.isNotBlank())Text("By ${e.who}",color=Slate500) } }}
        }
    }
}
