package com.senparmitech.attendancetracker.data.api

import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import com.senparmitech.attendancetracker.BuildConfig
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    private var retrofit: Retrofit? = null
    private var apiService: AttendanceApiService? = null

    fun resetClient() {
        retrofit = null
        apiService = null
    }

    fun getApiService(sessionManager: SessionManager): AttendanceApiService {
        if (apiService != null) return apiService!!

        val cookieJar = object : CookieJar {
            override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
                val cookieStrings = cookies.map { it.toString() }.toSet()
                if (cookieStrings.isNotEmpty()) {
                    sessionManager.saveCookies(cookieStrings)
                }
            }

            override fun loadForRequest(url: HttpUrl): List<Cookie> {
                val saved = sessionManager.getCookies()
                return saved.mapNotNull { Cookie.parse(url, it) }
            }
        }

        val builder = OkHttpClient.Builder()
            .cookieJar(cookieJar)
            .addInterceptor(ReauthInterceptor(sessionManager))
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)

        // Debug builds log the request line only. Bodies are never logged, because the
        // sign-in request contains the password.
        if (BuildConfig.DEBUG) {
            builder.addInterceptor(HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
                redactHeader("Cookie")
                redactHeader("Set-Cookie")
            })
        }
        val okHttpClient = builder.build()

        var baseUrl = sessionManager.getServerUrl()
        if (!baseUrl.endsWith("/")) {
            baseUrl += "/"
        }

        val newRetrofit = Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        retrofit = newRetrofit
        apiService = newRetrofit.create(AttendanceApiService::class.java)
        return apiService!!
    }
}
