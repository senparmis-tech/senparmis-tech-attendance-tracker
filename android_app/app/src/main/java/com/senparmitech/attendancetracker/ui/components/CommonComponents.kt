package com.senparmitech.attendancetracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.senparmitech.attendancetracker.ui.theme.*

@Composable
fun AcademicTopBar(
    title: String,
    subtitle: String? = "Senparmis Tech · Eclaro Academy",
    actions: @Composable RowScope.() -> Unit = {}
) {
    Surface(
        color = Navy900,
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    color = Slate50,
                    fontWeight = FontWeight.Bold
                )
                if (subtitle != null) {
                    Text(
                        text = subtitle,
                        style = MaterialTheme.typography.labelSmall,
                        color = Slate400,
                        fontSize = 10.5.sp
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                actions()
            }
        }
    }
}

@Composable
fun StatMetricCard(
    label: String,
    value: String,
    subText: String,
    modifier: Modifier = Modifier,
    accentColor: Color = Blue500
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Navy850),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate800),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = Slate400,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineMedium,
                color = Slate50,
                fontWeight = FontWeight.ExtraBold
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = subText,
                style = MaterialTheme.typography.labelSmall,
                color = Slate500,
                fontSize = 10.sp
            )
        }
    }
}

@Composable
fun AttendanceCodeBadge(code: String, modifier: Modifier = Modifier) {
    val (bgColor, textColor, label) = when (code.lowercase()) {
        "p" -> Triple(PresentBg, PresentGreen, "P")
        "x" -> Triple(AbsentBg, AbsentRed, "A")
        "l" -> Triple(LateBg, LateYellow, "L")
        "e" -> Triple(ExcusedBg, ExcusedBlue, "E")
        "r" -> Triple(RecitedBg, RecitedPurple, "R")
        else -> Triple(Navy800, Slate400, "—")
    }

    Box(
        modifier = modifier
            .background(bgColor, RoundedCornerShape(4.dp))
            .border(1.dp, textColor.copy(alpha = 0.3f), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = textColor,
            fontWeight = FontWeight.Bold,
            fontSize = 11.sp
        )
    }
}
