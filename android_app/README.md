# Senparmis Tech Attendance Tracker — Android Native Application

**Institution:** Eclaro Academy  
**Developer:** Senparmis Tech  
**Platform:** Android (API 26+ / Android 8.0 Oreo and above)  
**UI Toolkit:** Jetpack Compose (Material 3)  
**Architecture:** Modern Android Architecture (Repository pattern, Room Local DB, Retrofit REST API, Coroutines/Flow)

---

## Overview

This is the official native Android client for **Senparmis Tech Attendance Tracker**. It communicates directly with the Flask backend via session-cookie-authenticated REST APIs, offering teachers and academic administrators a fast, touch-friendly, mobile-optimized experience with offline drafting capabilities.

---

## Key Features

1. **Academic Dark Navy Interface**
   - Matches the web application's professional academic theme (Navy `#070D18`, `#0B1526`, Blue accent `#2563EB`, and Inter typography).
   - Designed for high readability during active classroom roll calls.

2. **Full Screen Coverage**
   - **Login Screen:** Secure role-based login with direct link to Server Settings.
   - **Dashboard Screen:** 2×3 Academic Overview metrics (Total Students, Total Subjects, Class Sections, Completed Sessions, Pending Roll Calls, Below 80% attendance) and real-time roll call status cards per subject/section.
   - **Mark Attendance (Roll Call):** High-priority mobile workflow with 5 Philippine academic marks (`P` Present, `A` Absent, `L` Late, `E` Excused, `R` Recited), live count pills, student search filter, topic note, and animated save dock.
   - **Offline Draft Persistence:** Roll call changes are saved immediately to local Room DB (`attendance_drafts`). If network drops or the teacher is temporarily offline, drafts are preserved and synced upon reconnection.
   - **Records Matrix:** Date-by-date attendance history with student summaries, attendance rates, and archived subject status alerts.
   - **Gradebook Screen:** Expandable student grade cards with Exam, Quiz, and Activity category scores, final percentages, and Philippine equivalent passing/failing marks.
   - **Subjects Management:** Browse active courses and expand section lists. Includes an **Archived Subjects** accordion to inspect historical records for completed terms.
   - **Student Lookup:** Fast search by student name or ID, displaying section enrollments, guardian contact details, and attendance/grade standings.
   - **Settings Screen:** Configurable Flask Server URL with instant switching between Android Emulator (`http://10.0.2.2:5000`), local LAN device (`http://192.168.x.x:5000`), or remote cloud deployment (e.g., PythonAnywhere `https://<username>.pythonanywhere.com`).

---

## Prerequisites

- **Android Studio:** Hedgehog (2023.1.1) or newer (Iguana, Jellyfish, Koala)
- **JDK:** Java 17 or Java 21 (bundled with Android Studio)
- **Android SDK:**
  - `minSdk`: 26 (Android 8.0)
  - `targetSdk`: 34 (Android 14)
  - `compileSdk`: 34

---

## Opening the Project in Android Studio

1. Open **Android Studio**.
2. Select **File > Open...** (or click **Open** on the Welcome screen).
3. Navigate to and select the `android_app` folder inside the project root:
   ```
   senparmis-tech-attendance-tracker/android_app
   ```
4. Click **OK**.
5. Wait for Android Studio to index the project and complete Gradle sync.
   - Gradle wrapper version: **8.7**
   - Android Gradle Plugin: **8.3.2**
   - Kotlin version: **1.9.23**

---

## Configuring the Server URL

The Android app can connect to local Flask development servers or cloud instances:

### 1. Default (Android Emulator)
By default, the app is pre-configured to:
```
http://10.0.2.2:5000
```
`10.0.2.2` is Android Emulator's alias to host machine's `127.0.0.1` / `localhost`.

### 2. Physical Device over Wi-Fi
If testing on a physical phone connected to the same Wi-Fi network:
1. Find your development machine's local IP (e.g., run `ipconfig` on Windows, look for IPv4 address like `192.168.1.100`).
2. Start the Flask server binding to `0.0.0.0`:
   ```bash
   py -3 app.py --host=0.0.0.0 --port=5000
   ```
3. Open the Android app, tap the **Settings** icon on the Login screen, enter `http://192.168.1.100:5000`, and tap **Save URL**.

### 3. Production / PythonAnywhere
Enter your live PythonAnywhere HTTPS URL in Settings:
```
https://<your-username>.pythonanywhere.com
```

---

## Network Security Configuration

The app includes `res/xml/network_security_config.xml` allowing cleartext HTTP traffic to `10.0.2.2`, `127.0.0.1`, and private IP ranges (`192.168.*.*`, `10.*.*.*`), ensuring hassle-free local development and emulator testing without HTTPS certificate errors.

---

## Project Structure

```
android_app/
├── app/
│   ├── build.gradle.kts                # Module dependencies (Compose, Retrofit, Room, etc.)
│   ├── proguard-rules.pro              # ProGuard configuration
│   └── src/main/
│       ├── AndroidManifest.xml         # Permissions & Activity declaration
│       ├── java/com/senparmitech/attendancetracker/
│       │   ├── AttendanceApp.kt        # Application class singleton
│       │   ├── data/
│       │   │   ├── api/
│       │   │   │   ├── ApiClient.kt             # OkHttp + CookieJar + Retrofit setup
│       │   │   │   ├── AttendanceApiService.kt  # REST endpoint definitions
│       │   │   │   ├── SessionManager.kt        # SharedPreferences & cookie persistence
│       │   │   │   └── models/ApiModels.kt      # Request/response DTOs
│       │   │   ├── local/
│       │   │   │   ├── AppDatabase.kt           # Room DB singleton
│       │   │   │   ├── AttendanceDraft.kt       # Offline draft entity
│       │   │   │   └── AttendanceDraftDao.kt    # Draft DAO operations
│       │   │   └── repository/
│       │   │       └── AttendanceRepository.kt  # Unified repository with offline cache sync
│       │   └── ui/
│       │       ├── MainActivity.kt              # Entry point Activity
│       │       ├── AppNavigation.kt             # Compose NavHost & Bottom Navigation
│       │       ├── components/CommonComponents.kt
│       │       ├── screens/
│       │       │   ├── DashboardScreen.kt
│       │       │   ├── GradebookScreen.kt
│       │       │   ├── LoginScreen.kt
│       │       │   ├── LookupScreen.kt
│       │       │   ├── MarkAttendanceScreen.kt
│       │       │   ├── RecordsScreen.kt
│       │       │   ├── SettingsScreen.kt
│       │       │   └── SubjectsScreen.kt
│       │       └── theme/
│       │           ├── Color.kt                 # Dark navy academic palette
│       │           ├── Theme.kt                 # Material 3 dark/light themes
│       │           └── Type.kt                  # Typography definitions
│       └── res/
│           ├── drawable/                        # Launcher backgrounds
│           ├── mipmap-anydpi-v26/               # Adaptive launcher icons
│           ├── values/                          # colors.xml, strings.xml, themes.xml
│           └── xml/                             # network_security_config.xml
├── build.gradle.kts                     # Root build script
├── gradle.properties                    # JVM arguments & AndroidX flags
├── settings.gradle.kts                  # Project name & module includes
└── gradle/wrapper/gradle-wrapper.properties
```

---

## API Integration Reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/login` | POST | Authenticates user credentials and establishes Flask session cookie |
| `/api/me` | GET | Returns current user role, display name, and monitor assignments |
| `/api/logout` | POST / GET | Terminates session |
| `/api/dashboard` | GET | Academic statistics (students, subjects, sections, roll calls) and cards |
| `/api/subjects` | GET | List of active subjects (with sections) and archived subjects |
| `/api/mark` | GET | Student roster and existing marks for a given subject, section, and date |
| `/save_attendance` | POST | Submits attendance marks and topic note |
| `/api/records` | GET | Attendance grid with date headers, student tallies, and percentage rates |
| `/api/grades` | GET | Gradebook categories, weights, max scores, and student scores |
| `/api/lookup` | GET | Student lookup by name or ID with guardian info and subject standing |
