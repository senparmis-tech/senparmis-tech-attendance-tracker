package com.senparmitech.attendancetracker.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
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
    object Students    : Screen("manage/students")
    object Terms       : Screen("manage/terms")
    object ActivityLog : Screen("manage/activity")
    object Accounts    : Screen("manage/accounts")
    object GradeSetupPicker : Screen("manage/grade-setup")
    object GradeSetup  : Screen("manage/grade-setup/{subject}/{section}") {
        fun route(subject: String, section: String) = "manage/grade-setup/${URLEncoder.encode(subject, "UTF-8")}/${URLEncoder.encode(section, "UTF-8")}"
    }
    object ScoreRollCall : Screen("manage/score-roll-call/{subject}/{section}/{itemId}") {
        fun route(subject: String, section: String, itemId: Int) = "manage/score-roll-call/${URLEncoder.encode(subject, "UTF-8")}/${URLEncoder.encode(section, "UTF-8")}/$itemId"
    }
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
    BottomNavItem("Subjects",  Icons.Default.MenuBook, Screen.Subjects),
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

    // If the saved session can no longer be renewed, go back to the sign-in screen.
    val loggedIn by sessionManager.isLoggedInState.collectAsState()
    LaunchedEffect(loggedIn) {
        if (!loggedIn && navController.currentDestination?.route != Screen.Login.route) {
            navController.navigate(Screen.Login.route) {
                popUpTo(0) { inclusive = true }
            }
        }
    }

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
                LookupScreen(
                    onNavigateBack = { navController.popBackStack() }
                )
            }

            // ── Settings ──────────────────────────────────────────────────────
            composable(Screen.Settings.route) {
                SettingsScreen(
                    onNavigateBack = { navController.popBackStack() },
                    onManageStudents = { navController.navigate(Screen.Students.route) },
                    onManageTerms = { navController.navigate(Screen.Terms.route) },
                    onManageActivity = { navController.navigate(Screen.ActivityLog.route) },
                    onManageAccounts = { navController.navigate(Screen.Accounts.route) },
                    onManageGrades = { navController.navigate(Screen.GradeSetupPicker.route) },
                    onLogout = {
                        navController.navigate(Screen.Login.route) {
                            popUpTo(0) { inclusive = true }
                        }
                    }
                )
            }

            composable(Screen.Students.route) { StudentsScreen() }
            composable(Screen.Terms.route) { TermsScreen(onBack = { navController.popBackStack() }) }
            composable(Screen.ActivityLog.route) { ActivityLogScreen(onBack = { navController.popBackStack() }) }
            composable(Screen.Accounts.route) { AccountsScreen(onBack = { navController.popBackStack() }) }
            composable(Screen.GradeSetupPicker.route) {
                GradeSetupPickerScreen(onBack = { navController.popBackStack() }, onPick = { s, sec -> navController.navigate(Screen.GradeSetup.route(s, sec)) })
            }
            composable(Screen.GradeSetup.route, arguments = listOf(navArgument("subject") { type = NavType.StringType }, navArgument("section") { type = NavType.StringType })) { entry ->
                val s = URLDecoder.decode(entry.arguments?.getString("subject") ?: "", "UTF-8")
                val sec = URLDecoder.decode(entry.arguments?.getString("section") ?: "", "UTF-8")
                GradeSetupScreen(s, sec, onNavigateBack = { navController.popBackStack() }, onRollCall = { id -> navController.navigate(Screen.ScoreRollCall.route(s, sec, id)) })
            }
            composable(Screen.ScoreRollCall.route, arguments = listOf(navArgument("subject") { type = NavType.StringType }, navArgument("section") { type = NavType.StringType }, navArgument("itemId") { type = NavType.IntType })) { entry ->
                val s = URLDecoder.decode(entry.arguments?.getString("subject") ?: "", "UTF-8")
                val sec = URLDecoder.decode(entry.arguments?.getString("section") ?: "", "UTF-8")
                ScoreRollCallScreen(s, sec, entry.arguments?.getInt("itemId") ?: 0, onNavigateBack = { navController.popBackStack() })
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
                    initialSubject = subject,
                    initialSection = section,
                    initialDate = date,
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
                    initialSubject = subject,
                    initialSection = section,
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
                    initialSubject = subject,
                    initialSection = section,
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
