package com.senparmitech.attendancetracker.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val DarkColorScheme = darkColorScheme(
    primary = Blue500,
    onPrimary = Slate50,
    primaryContainer = Navy800,
    onPrimaryContainer = Slate50,
    secondary = Blue400,
    background = Navy950,
    onBackground = Slate50,
    surface = Navy900,
    onSurface = Slate50,
    surfaceVariant = Navy850,
    onSurfaceVariant = Slate400,
    outline = Slate800
)

private val LightColorScheme = lightColorScheme(
    primary = Blue600,
    onPrimary = Slate50,
    primaryContainer = Slate200,
    onPrimaryContainer = Navy900,
    secondary = Blue500,
    background = Slate50,
    onBackground = Navy950,
    surface = Slate50,
    onSurface = Navy950,
    surfaceVariant = Slate200,
    onSurfaceVariant = Slate700,
    outline = Slate200
)

@Composable
fun AttendanceTrackerTheme(
    darkTheme: Boolean = true, // Default to dark navy theme
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = Navy950.toArgb()
            window.navigationBarColor = Navy950.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
