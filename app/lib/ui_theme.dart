import 'package:flutter/material.dart';

ThemeData localVoiceTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF075747),
    primary: const Color(0xFF075747),
    secondary: const Color(0xFF739C85),
    surface: const Color(0xFFFBFAF5),
  );
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    scaffoldBackgroundColor: scheme.surface,
    appBarTheme: AppBarTheme(backgroundColor: scheme.surface, surfaceTintColor: Colors.transparent),
    cardTheme: CardThemeData(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: Color(0xFFE1E7DF)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
    ),
    // Room for the 24px S1 icons used as chip avatars.
    chipTheme: const ChipThemeData(avatarBoxConstraints: BoxConstraints.tightFor(width: 24, height: 24)),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
  );
}
