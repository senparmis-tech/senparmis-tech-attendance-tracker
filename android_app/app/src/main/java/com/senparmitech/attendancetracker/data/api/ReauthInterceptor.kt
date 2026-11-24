package com.senparmitech.attendancetracker.data.api

import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject

/**
 * The server session lasts 12 hours. When a request comes back 401, sign in again with the
 * saved credentials and repeat the request once. If that sign-in is refused (for example the
 * password was changed), the saved session is cleared so the app returns to the login screen.
 */
class ReauthInterceptor(private val session: SessionManager) : Interceptor {

    private val lock = Any()

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val response = chain.proceed(request)
        if (response.code != 401 || request.url.encodedPath == LOGIN_PATH) return response

        val creds = session.getCredentials()
        if (creds == null) {
            session.clearSession()
            return response
        }

        synchronized(lock) {
            val body = JSONObject()
                .put("username", creds.first)
                .put("password", creds.second)
                .toString()
                .toRequestBody("application/json".toMediaType())
            val loginRequest: Request = Request.Builder()
                .url(request.url.newBuilder().encodedPath(LOGIN_PATH).query(null).build())
                .post(body)
                .build()
            val loginOk = chain.proceed(loginRequest).use { it.isSuccessful }
            if (!loginOk) {
                session.clearSession()
                return response
            }
        }
        response.close()
        return chain.proceed(request)
    }

    private companion object {
        const val LOGIN_PATH = "/api/login"
    }
}
