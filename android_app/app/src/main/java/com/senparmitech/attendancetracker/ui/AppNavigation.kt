package com.senparmitech.attendancetracker.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.LibraryBooks
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.senparmitech.attendancetracker.AttendanceApp
import com.senparmitech.attendancetracker.ui.screens.*
import com.senparmitech.attendancetracker.ui.theme.*
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

// ─── Route definitions ───────────────────────────────────────────────────────

sealed class Screen(val route: String) {
    object Login       : Screen("login")
    object Dashboard   : Screen("dashboard")
    object Subjects    : Screen("subjects")
    object Lookup      : Screen("lookup")
    object Settings    : Screen("settings")
    object Mark        : Screen("mark/{subject}/{section}/{date}") {
        fun route(subject: String, section: String, date: String): String {
            val encS = URLEncoder.encode(subject, StandardCharsets.UTF_8.toString())
            val encSec = URLEncoder.encode(section, StandardCharsets.UTF_8.toString())
            val encD = URLEncoder.encode(date, StandardCharsets.UTF_8.toString())
            return "mark/$encS/$encSec/$encD"
        }
    }
    object Records     : Screen("records/{subject}/{section}") {
        fun route(subject: String, section: String): String {
            val encS = URLEncoder.encode(subject, StandardCharsets.UTF_8.toString())
            val encSec = URLEncoder.encode(section, StandardCharsets.UTF_8.toString())
            return "records/$encS/$encSec"
        }
    }
    object Grades      : Screen("grades/{subject}/{section}") {
        fun route(subject: String, section: String): String {
            val encS = URLEncoder.encode(subject, StandardCharsets.UTF_8.toString())
            val encSec = URLEncoder.encode(section, StandardCharsets.UTF_8.toString())
            return "grades/$encS/$encSec"
        }
    }
}

// ─── Bottom Navigation items ──────────────────────────────────────────────────

data class BottomNavItem(
    val label: String,
    val icon: ImageVector,
    val screen: Screen
)

val bottomNavItems = listOf(
    BottomNavItem("Dashboard", Icons.Default.Dashboard, Screen.Dashboard),
    BottomNavItem("Subjects",  Icons.Default.LibraryBooks, Screen.Subjects),
    BottomNavItem("Lookup",    Icons.Default.Search, Screen.Lookup),
    BottomNavItem("Settings",  Icons.Default.Person, Screen.Settings)
)

// Routes where the bottom nav is visible
private val bottomNavRoutes = setOf(
    Screen.Dashboard.route,
    Screen.Subjects.route,
    Screen.Lookup.route,
    Screen.Settings.route
)

// ─── Root composable ──────────────────────────────────────────────────────────

@Composable
fun AppNavigation() {
    val sessionManager = AttendanceApp.instance.sessionManager
    val navController: NavHostController = rememberNavController()

    val startDest = if (sessionManager.isLoggedIn()) Screen.Dashboard.route else Screen.Login.route

    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route
    val showBottomBar = currentRoute in bottomNavRoutes

    Scaffold(
        containerColor = Navy950,
        bottomBar = {
            if (showBottomBar) {
                BottomNavigationBar(navController = navController)
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = startDest,
            modifier = Modifier.padding(innerPadding)
        ) {
            // ── Login ─────────────────────────────────────────────────────────
            composable(Screen.Login.route) {
                LoginScreen(
                    onLoginSuccess = {
                        navController.navigate(Screen.Dashboard.route) {
                            popUpTo(Screen.Login.route) { inclusive = true }
                        }
                    },
                    onNavigateToSettings = {
                        navController.navigate(Screen.Settings.route)
                    }
                )
            }

            // ── Dashboard ─────────────────────────────────────────────────────
            composable(Screen.Dashboard.route) {
                DashboardScreen(
                    onNavigateToMark = { subject, section, date ->
                        navController.navigate(Screen.Mark.route(subject, section, date))
                    },
                    onNavigateToRecords = { subject, section ->
                        navController.navigate(Screen.Records.route(subject, section))
                    },
                    onNavigateToGrades = { subject, section ->
                        navController.navigate(Screen.Grades.route(subject, section))
                    }
                )
            }

            // ── Subjects ──────────────────────────────────────────────────────
            composable(Screen.Subjects.route) {
                SubjectsScreen(
                    onNavigateToMark = { subject, section, date ->
                        navController.navigate(Screen.Mark.route(subject, section, date))
                    },
                    onNavigateToRecords = { subject, section ->
                        navController.navigate(Screen.Records.route(subject, section))
                    },
                    onNavigateToGrades = { subject, section ->
                        navController.navigate(Screen.Grades.route(subject, section))
                    }
                )
            }

            // ── Lookup ────────────────────────────────────────────────────────
            composable(Screen.Lookup.route) {
                LookupScreen()
            }

            // ── Settings ──────────────────────────────────────────────────────
            composable(Screen.Settings.route) {
                SettingsScreen(
                    onNavigateBack = { navController.popBackStack() },
                    onLogout = {
                        navController.navigate(Screen.Login.route) {
                            popUpTo(0) { inclusive = true }
                        }
                    }
                )
            }

            // ── Mark Attendance ───────────────────────────────────────────────
            composable(
                route = Screen.Mark.route,
                arguments = listOf(
                    navArgument("subject") { type = NavType.StringType },
                    navArgument("section") { type = NavType.StringType },
                    navArgument("date")    { type = NavType.StringType }
                )
            ) { backStackEntry ->
                val subject = URLDecoder.decode(backStackEntry.arguments?.getString("subject") ?: "", "UTF-8")
                val section = URLDecoder.decode(backStackEntry.arguments?.getString("section") ?: "", "UTF-8")
                val date    = URLDecoder.decode(backStackEntry.arguments?.getString("date") ?: "", "UTF-8")
                MarkAttendanceScreen(
                    subject = subject,
                    section = section,
                    dateIso = date,
                    onNavigateBack = { navController.popBackStack() }
                )
            }

            // ── Records ───────────────────────────────────────────────────────
            composable(
                route = Screen.Records.route,
                arguments = listOf(
                    navArgument("subject") { type = NavType.StringType },
                    navArgument("section") { type = NavType.StringType }
                )
            ) { backStackEntry ->
                val subject = URLDecoder.decode(backStackEntry.arguments?.getString("subject") ?: "", "UTF-8")
                val section = URLDecoder.decode(backStackEntry.arguments?.getString("section") ?: "", "UTF-8")
                RecordsScreen(
                    subject = subject,
                    section = section,
                    onNavigateBack = { navController.popBackStack() }
                )
            }

            // ── Gradebook ─────────────────────────────────────────────────────
            composable(
                route = Screen.Grades.route,
                arguments = listOf(
                    navArgument("subject") { type = NavType.StringType },
                    navArgument("section") { type = NavType.StringType }
                )
            ) { backStackEntry ->
                val subject = URLDecoder.decode(backStackEntry.arguments?.getString("subject") ?: "", "UTF-8")
                val section = URLDecoder.decode(backStackEntry.arguments?.getString("section") ?: "", "UTF-8")
                GradebookScreen(
                    subject = subject,
                    section = section,
                    onNavigateBack = { navController.popBackStack() }
                )
            }
        }
    }
}

// ─── Bottom Navigation Bar ────────────────────────────────────────────────────

@Composable
fun BottomNavigationBar(navController: NavHostController) {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination

    NavigationBar(
        containerColor = Navy900,
        contentColor = Slate400,
        tonalElevation = 0.dp
    ) {
        bottomNavItems.forEach { item ->
            val selected = currentDestination?.hierarchy?.any { it.route == item.screen.route } == true
            NavigationBarItem(
                selected = selected,
                onClick = {
                    if (!selected) {
                        navController.navigate(item.screen.route) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                },
                icon = {
                    Icon(
                        imageVector = item.icon,
                        contentDescription = item.label,
                        tint = if (selected) Blue400 else Slate500
                    )
                },
                label = {
                    Text(
                        text = item.label,
                        fontSize = 10.sp,
                        fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                        color = if (selected) Blue400 else Slate500
                    )
                },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = Blue400,
                    selectedTextColor = Blue400,
                    unselectedIconColor = Slate500,
                    unselectedTextColor = Slate500,
                    indicatorColor = Navy800
                )
            )
        }
    }
}
