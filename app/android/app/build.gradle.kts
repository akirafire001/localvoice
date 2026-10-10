import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val uploadKeyProperties = Properties()
val uploadKeyPropertiesFile = rootProject.file("key.properties")
if (uploadKeyPropertiesFile.exists()) {
    uploadKeyPropertiesFile.inputStream().use { uploadKeyProperties.load(it) }
}

android {
    namespace = "com.localvoice.localvoice"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // Required by flutter_local_notifications (java.time APIs on older Android)
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        // Registered package in Google Play Console.
        applicationId = "tech.ideaworks.localvoice"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // Shared development key so every machine builds with the same SHA-1, which is
    // registered for the Android OAuth client in Google Cloud. Not for store releases.
    signingConfigs {
        getByName("debug") {
            storeFile = file("dev.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
        create("release") {
            storeFile = uploadKeyProperties.getProperty("storeFile")?.let { file(it) }
            storePassword = uploadKeyProperties.getProperty("storePassword")
            keyAlias = uploadKeyProperties.getProperty("keyAlias")
            keyPassword = uploadKeyProperties.getProperty("keyPassword")
        }
    }

    buildTypes {
        release {
            // Never upload a development-key-signed build to Google Play.
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
