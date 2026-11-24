# Proguard rules for Senparmis Tech Attendance Tracker
-keepattributes *Annotation*
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}
