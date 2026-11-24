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
import com.senparmitech.attendancetracker.data.api.models.TeacherItem
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable fun AccountsScreen(onBack:()->Unit) {
    val app=AttendanceApp.instance; val scope= rememberCoroutineScope(); val admin=app.sessionManager.isAdmin()
    var teachers by remember{mutableStateOf(emptyList<TeacherItem>())}; var isAdmin by remember{mutableStateOf(admin)}; var selfId by remember{mutableStateOf<Int?>(null)}; var loading by remember{mutableStateOf(true)}; var error by remember{mutableStateOf<String?>(null)}; var form by remember{mutableStateOf("")}; var target by remember{mutableStateOf<TeacherItem?>(null)}
    fun load(){loading=true;scope.launch{val r=app.manage.teachers();loading=false;if(r.isSuccess){val d=r.getOrNull()!!;teachers=d.teachers;isAdmin=d.is_admin;selfId=d.self_id;error=null}else error=r.exceptionOrNull()?.message}}
    fun act(path:String,fields:Map<String,Any?>){scope.launch{val e=app.manage.act(path,*fields.entries.map{it.key to it.value}.toTypedArray());if(e==null){form="";target=null;load()}else error=e}}
    LaunchedEffect(Unit){load()}
    if(form=="add") FormDialog("Add account",listOf("Username","Display name","Password","Role: teacher/admin/monitor","Monitor section ID (optional)"),password=setOf(2),note="Monitor section ID is required for monitors.",onDismiss={form=""}){v->act("/api/teacher_add",mapOf("username" to v[0],"display_name" to v[1],"password" to v[2],"is_admin" to v[3].equals("admin",true),"is_monitor" to v[3].equals("monitor",true),"monitor_section_id" to v[4].toIntOrNull()))}
    if(form=="password") FormDialog("Change password",listOf("New password"),password=setOf(0),onDismiss={form=""}){v->act("/api/teacher_password",mapOf("teacher_id" to (target?.id?:selfId),"password" to v[0]))}
    if(form=="assign") FormDialog("Assign subject",listOf("Subject name","Teacher ID (blank for unassigned)"),initial=listOf("",""),onDismiss={form=""}){v->act("/api/teacher_assign",mapOf("subject" to v[0],"teacher_id" to v[1].toIntOrNull()))}
    target?.takeIf{form=="delete"}?.let{t->ConfirmDialog("Remove ${t.display_name}?","This account will be deleted.","Remove",onDismiss={target=null;form=""}){act("/api/teacher_delete",mapOf("teacher_id" to t.id))}}
    Scaffold(topBar={AcademicTopBar("Accounts",if(isAdmin) "Teachers and access" else "Your account") { IconButton(onClick=onBack){Icon(Icons.Default.ArrowBack,null,tint=Slate400)} }}){pad->
        Column(Modifier.fillMaxSize().padding(pad).padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
            if(loading)LinearProgressIndicator(Modifier.fillMaxWidth());error?.let{Text(it,color=AbsentRed)}
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Button(onClick={target=null;form="password"},colors=ButtonDefaults.buttonColors(containerColor=Blue600)){Text("Change my password")};if(isAdmin){Button(onClick={form="add"},colors=ButtonDefaults.buttonColors(containerColor=Blue600)){Text("Add account")};OutlinedButton(onClick={form="assign"}){Text("Assign subject")}}}
            if(isAdmin) LazyColumn(verticalArrangement=Arrangement.spacedBy(8.dp)){items(teachers){t->Panel{Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Column(Modifier.weight(1f)){Text(t.display_name,color=Slate50,fontWeight=FontWeight.Bold);Text("@${t.username} · ${when{t.is_admin!=0->"Admin";t.is_monitor!=0->"Monitor";else->"Teacher"}} · ${t.n_subjects} subjects",color=Slate400);if(t.monitor_section_name!=null)Text("Monitor: ${t.monitor_section_name}",color=Blue400)};TextButton(onClick={target=t;form="password"}){Text("Password")};if(t.id!=selfId)TextButton(onClick={target=t;form="delete"}){Text("Remove",color=AbsentRed)}}} }}
        }
    }
}
