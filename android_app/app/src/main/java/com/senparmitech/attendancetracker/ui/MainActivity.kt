package com.senparmitech.attendancetracker.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.senparmitech.attendancetracker.ui.theme.AttendanceTrackerTheme
import com.senparmitech.attendancetracker.ui.theme.Navy950

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AttendanceTrackerTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Navy950
                ) {
                    AppNavigation()
                }
            }
        }
    }
}
