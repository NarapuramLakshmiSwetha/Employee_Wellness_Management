# Wellness Hub - Android Mobile Application

This is the native Android mobile application wrapper for the **Employee Wellness Management System**. It loads your Flask web application portal inside a full-screen WebView with support for sessions, native back button navigation, pull-to-refresh, and profile photo uploads (camera & gallery permissions).

---

## Prerequisites

1. **Android Studio:** Install [Android Studio](https://developer.android.com/studio) to compile and build the app.
2. **Wi-Fi Network:** Make sure your mobile phone and your computer running the Flask server are connected to the **same Wi-Fi network**.

---

## Quick Start: Build the App in Android Studio

1. **Open Project:**
   - Launch Android Studio.
   - Click **Open** and select the `mobile_app` folder inside your project directory.
   - Android Studio will automatically detect the project, configure Gradle, and download the required Android SDK Platform (API 34).

2. **Run on a Phone/Emulator:**
   - Connect your Android phone to your PC via USB with **USB Debugging** enabled (in Developer Options).
   - Alternatively, create a virtual device (Emulator) in Android Studio Device Manager.
   - Click the green **Run (Play)** button in Android Studio to install and run the app.

3. **Build the APK (To share with friends):**
   - In Android Studio, go to **Build > Build Bundle(s) / APK(s) > Build APK(s)**.
   - Once compilation is complete, click **Locate** in the bottom-right notification popup.
   - Copy the `app-debug.apk` file to your mobile phone or share it with your friends via WhatsApp, Email, or Google Drive, and install it!

---

## Connecting the App to your Flask Server

### Step 1: Start the Flask Server
Run the Flask server on your computer. Note that `app.py` has been configured to listen on `0.0.0.0`, allowing network devices to connect.
```bash
python app.py
```

### Step 2: Find your Computer's IP Address
Open Command Prompt (`cmd`) on your computer and run:
```cmd
ipconfig
```
Look for **IPv4 Address** under your active Wi-Fi adapter (it will look like `192.168.x.x` or `10.0.x.x`).

### Step 3: Connect the App
1. Open the **Employee Wellness Hub** app on your phone.
2. You will be greeted by the **Server Config** onboarding screen.
3. Enter your computer's IP address and port 5000:
   `http://192.168.x.x:5000` (replace `192.168.x.x` with your actual IP address).
4. Tap **Connect to Portal**. The app will remember this URL, so you only have to do this once!
