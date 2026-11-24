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
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.ui.theme.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LoginScreen(
    onLoginSuccess: () -> Unit,
    onNavigateToSettings: () -> Unit
) {
    val repository = AttendanceApp.instance.repository
    val sessionManager = AttendanceApp.instance.sessionManager
    val scope = rememberCoroutineScope()

    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isPasswordVisible by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    val serverUrl by sessionManager.serverUrlState.collectAsState()

    fun doLogin() {
        if (password.isBlank()) {
            errorMessage = "Please enter your password."
            return
        }
        isLoading = true
        errorMessage = null
        scope.launch {
            val result = repository.login(password.trim(), username.trim())
            isLoading = false
            if (result.isSuccess) {
                onLoginSuccess()
            } else {
                errorMessage = result.exceptionOrNull()?.message ?: "Sign-in failed."
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Academic Portal Sign-In", fontSize = 16.sp, fontWeight = FontWeight.Bold) },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Navy900,
                    titleContentColor = Slate50
                ),
                actions = {
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Server Settings", tint = Slate400)
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
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(modifier = Modifier.height(16.dp))

            // Institution Branding Card
            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .background(Blue600, RoundedCornerShape(8.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            Text("EA", color = Slate50, fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
                        }
                        Spacer(modifier = Modifier.width(12.dp))
                        Column {
                            Text("Eclaro Academy", fontWeight = FontWeight.ExtraBold, fontSize = 16.sp, color = Slate50)
                            Text("Academic Information System", fontSize = 11.5.sp, color = Slate400)
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "Senparmis Tech Attendance Tracker",
                        fontSize = 12.5.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Blue400
                    )
                    Text(
                        text = "Academic Records. Organized and Accessible.",
                        fontSize = 11.sp,
                        color = Slate500,
                        modifier = Modifier.padding(top = 2.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Server Indicator
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Navy850, RoundedCornerShape(6.dp))
                    .border(1.dp, Slate800, RoundedCornerShape(6.dp))
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text("Server Target", fontSize = 10.sp, color = Slate400, fontWeight = FontWeight.Bold)
                    Text(serverUrl, fontSize = 12.sp, color = Slate200)
                }
                TextButton(onClick = onNavigateToSettings) {
                    Text("Change", fontSize = 11.5.sp, color = Blue400)
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Login Card
            Card(
                colors = CardDefaults.cardColors(containerColor = Navy900),
                border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = "Account Credentials",
                        style = MaterialTheme.typography.titleMedium,
                        color = Slate50,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Sign in with faculty credentials, monitor account, or school password.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Slate400,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(top = 2.dp, bottom = 16.dp)
                    )

                    OutlinedTextField(
                        value = username,
                        onValueChange = { username = it },
                        label = { Text("Username (Optional for admin password)") },
                        leadingIcon = { Icon(Icons.Default.Person, contentDescription = null, tint = Slate400) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Blue500,
                            unfocusedBorderColor = Slate800,
                            focusedTextColor = Slate50,
                            unfocusedTextColor = Slate50
                        )
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password") },
                        leadingIcon = { Icon(Icons.Default.Lock, contentDescription = null, tint = Slate400) },
                        trailingIcon = {
                            IconButton(onClick = { isPasswordVisible = !isPasswordVisible }) {
                                Icon(
                                    imageVector = if (isPasswordVisible) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                    contentDescription = null,
                                    tint = Slate400
                                )
                            }
                        },
                        visualTransformation = if (isPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { doLogin() }),
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Blue500,
                            unfocusedBorderColor = Slate800,
                            focusedTextColor = Slate50,
                            unfocusedTextColor = Slate50
                        )
                    )

                    if (errorMessage != null) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = errorMessage!!,
                            color = AbsentRed,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    Button(
                        onClick = { doLogin() },
                        enabled = !isLoading,
                        colors = ButtonDefaults.buttonColors(containerColor = Blue600),
                        shape = RoundedCornerShape(6.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp)
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(color = Slate50, modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                        } else {
                            Text("Sign In to Attendance System", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Guidance footer
            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "Supported Roles: Admin · Faculty Instructor · Section Monitor · Student",
                    fontSize = 11.sp,
                    color = Slate500
                )
            }
        }
    }
}
