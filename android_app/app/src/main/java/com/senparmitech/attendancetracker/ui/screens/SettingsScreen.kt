package com.senparmitech.attendancetracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.data.api.ApiClient
import com.senparmitech.attendancetracker.ui.components.AcademicTopBar
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(
    onNavigateBack: () -> Unit,
    onLogout: () -> Unit
) {
    val sessionManager = AttendanceApp.instance.sessionManager
    val repository = AttendanceApp.instance.repository
    val scope = rememberCoroutineScope()
    val focusManager = LocalFocusManager.current

    var serverUrl by remember { mutableStateOf(sessionManager.getServerUrl()) }
    var urlSaved by remember { mutableStateOf(false) }
    var urlError by remember { mutableStateOf<String?>(null) }

    var userProfile by remember { mutableStateOf<String?>(null) }
    var userRole by remember { mutableStateOf<String?>(null) }

    var logoutDialogOpen by remember { mutableStateOf(false) }
    var isLoggingOut by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        val profile = repository.getMe()
        if (profile.isSuccess) {
            val p = profile.getOrNull()
            userProfile = p?.display_name ?: sessionManager.getUsername()
            userRole = when {
                p?.is_admin == true -> "Administrator"
                p?.is_monitor == true -> "Monitor"
                p?.role == "student" -> "Student"
                else -> "Teacher"
            }
        }
    }

    if (logoutDialogOpen) {
        AlertDialog(
            onDismissRequest = { logoutDialogOpen = false },
            containerColor = Navy850,
            titleContentColor = Slate50,
            textContentColor = Slate400,
            title = { Text("Sign Out", fontWeight = FontWeight.Bold) },
            text = { Text("Are you sure you want to sign out of your account?") },
            confirmButton = {
                Button(
                    onClick = {
                        logoutDialogOpen = false
                        isLoggingOut = true
                        scope.launch {
                            repository.logout()
                            sessionManager.clearSession()
                            onLogout()
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = AbsentRed.copy(alpha = 0.8f)),
                    enabled = !isLoggingOut
                ) {
                    if (isLoggingOut) {
                        CircularProgressIndicator(modifier = Modifier.size(16.dp), color = Slate50, strokeWidth = 2.dp)
                    } else {
                        Text("Sign Out", fontWeight = FontWeight.Bold)
                    }
                }
            },
            dismissButton = {
                OutlinedButton(
                    onClick = { logoutDialogOpen = false },
                    border = androidx.compose.foundation.BorderStroke(1.dp, Slate700)
                ) {
                    Text("Cancel", color = Slate200)
                }
            }
        )
    }

    Scaffold(
        topBar = {
            AcademicTopBar(
                title = "Settings",
                subtitle = "Application Configuration",
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
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Account section
            SectionHeader(icon = Icons.Default.Person, title = "ACCOUNT")

            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = userProfile ?: "Loading...",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate50
                    )
                    if (userRole != null) {
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = userRole!!,
                            style = MaterialTheme.typography.bodySmall,
                            color = Blue400,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "Eclaro Academy · Senparmis Tech",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400,
                        fontSize = 11.sp
                    )
                }
            }

            // Server Configuration section
            SectionHeader(icon = Icons.Default.Link, title = "SERVER CONFIGURATION")

            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Flask Server URL",
                        style = MaterialTheme.typography.labelMedium,
                        color = Slate200,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Enter the base URL of your Senparmis Tech backend server. Use the LAN IP or PythonAnywhere domain.",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate500,
                        fontSize = 11.sp
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = serverUrl,
                        onValueChange = {
                            serverUrl = it
                            urlSaved = false
                            urlError = null
                        },
                        label = { Text("Server URL", color = Slate500) },
                        placeholder = { Text("http://10.0.2.2:5000", color = Slate700) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Uri,
                            imeAction = ImeAction.Done
                        ),
                        keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = Slate50,
                            unfocusedTextColor = Slate200,
                            focusedBorderColor = Blue500,
                            unfocusedBorderColor = Slate700,
                            cursorColor = Blue400,
                            focusedLabelColor = Blue400,
                            unfocusedLabelColor = Slate500,
                            focusedContainerColor = Navy800,
                            unfocusedContainerColor = Navy800
                        ),
                        isError = urlError != null,
                        supportingText = urlError?.let { { Text(it, color = AbsentRed, fontSize = 11.sp) } }
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                val trimmed = serverUrl.trimEnd('/')
                                if (trimmed.isEmpty()) {
                                    urlError = "URL cannot be empty."
                                    return@Button
                                }
                                if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
                                    urlError = "URL must start with http:// or https://"
                                    return@Button
                                }
                                sessionManager.setServerUrl(trimmed)
                                serverUrl = trimmed
                                ApiClient.resetClient()
                                urlSaved = true
                                urlError = null
                                focusManager.clearFocus()
                            },
                            shape = RoundedCornerShape(6.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Blue600),
                            modifier = Modifier.weight(1f)
                        ) {
                            if (urlSaved) {
                                Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Saved!", fontWeight = FontWeight.Bold)
                            } else {
                                Icon(Icons.Default.Save, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Save URL", fontWeight = FontWeight.Bold)
                            }
                        }
                        OutlinedButton(
                            onClick = {
                                val defaultUrl = "http://10.0.2.2:5000"
                                serverUrl = defaultUrl
                                sessionManager.setServerUrl(defaultUrl)
                                ApiClient.resetClient()
                                urlSaved = true
                                urlError = null
                            },
                            shape = RoundedCornerShape(6.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, Slate700)
                        ) {
                            Text("Reset Default", color = Slate400, fontSize = 12.sp)
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Navy800, RoundedCornerShape(6.dp))
                            .border(1.dp, Slate800, RoundedCornerShape(6.dp))
                            .padding(10.dp)
                    ) {
                        Column {
                            Text("Quick URLs:", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Slate500)
                            Spacer(modifier = Modifier.height(2.dp))
                            Text("Emulator: http://10.0.2.2:5000", fontSize = 10.sp, color = Slate500)
                            Text("Local device: http://192.168.x.x:5000", fontSize = 10.sp, color = Slate500)
                            Text("PythonAnywhere: https://yourname.pythonanywhere.com", fontSize = 10.sp, color = Slate500)
                        }
                    }
                }
            }

            // App Information section
            SectionHeader(icon = Icons.Default.Settings, title = "APPLICATION")

            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    InfoRow("Application", "Senparmis Tech Attendance Tracker")
                    InfoRow("Institution", "Eclaro Academy")
                    InfoRow("Developer", "Senparmis Tech")
                    InfoRow("Build Target", "Android API 26+")
                    InfoRow("Auth Method", "Session Cookie (Flask)")
                    InfoRow("Offline Support", "Room DB Draft Cache")
                }
            }

            // Sign Out button
            Spacer(modifier = Modifier.height(4.dp))
            Button(
                onClick = { logoutDialogOpen = true },
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Navy800),
                border = androidx.compose.foundation.BorderStroke(1.dp, AbsentRed.copy(alpha = 0.4f)),
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Default.Logout, contentDescription = null, tint = AbsentRed, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Sign Out", color = AbsentRed, fontWeight = FontWeight.Bold)
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun SectionHeader(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = Slate500, modifier = Modifier.size(14.dp))
        Spacer(modifier = Modifier.width(6.dp))
        Text(
            text = title,
            style = MaterialTheme.typography.labelSmall,
            color = Slate400,
            fontWeight = FontWeight.Bold,
            fontSize = 11.sp
        )
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(text = label, fontSize = 12.sp, color = Slate500)
        Text(text = value, fontSize = 12.sp, color = Slate200, fontWeight = FontWeight.Medium)
    }
}
