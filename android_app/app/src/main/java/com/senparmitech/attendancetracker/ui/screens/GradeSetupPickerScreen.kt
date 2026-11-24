package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.models.SubjectItem
import com.senparmitech.attendancetracker.ui.components.*
import com.senparmitech.attendancetracker.ui.theme.*

@Composable fun GradeSetupPickerScreen(onBack:()->Unit,onPick:(String,String)->Unit){
 val repo=AttendanceApp.instance.repository;var subjects by remember{mutableStateOf(emptyList<SubjectItem>())};var subject by remember{mutableStateOf("")};var section by remember{mutableStateOf("")}
 LaunchedEffect(Unit){val r=repo.getSubjects();if(r.isSuccess){subjects=r.getOrNull()?.subjects.orEmpty();subject=subjects.firstOrNull()?.name.orEmpty();section=subjects.firstOrNull()?.sections?.firstOrNull().orEmpty()}}
 Scaffold(topBar={AcademicTopBar("Grade setup","Choose a subject and section"){IconButton(onClick=onBack){Icon(Icons.Default.ArrowBack,null,tint=Slate400)}}}){p->Column(Modifier.fillMaxSize().padding(p).padding(16.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){SubjectSectionPicker(subjects,subject,section){s,c->subject=s;section=c};Button(onClick={onPick(subject,section)},enabled=subject.isNotBlank(),colors=ButtonDefaults.buttonColors(containerColor=Blue600)){Text("Open grade setup")}}}
}
