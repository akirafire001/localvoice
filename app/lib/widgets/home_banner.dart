import 'dart:math';

import 'package:flutter/material.dart';

/// Offline artwork for the home screen: two retained sketches and 20 landmarks.
enum LvHomeBanner {
  neighborhood('pencil-neighborhood'),
  coast('pencil-coast'),
  mountFuji('japan-fuji'),
  greatWall('china-great-wall'),
  gyeongbokgung('korea-gyeongbokgung'),
  tajMahal('india-taj-mahal'),
  angkorWat('cambodia-angkor-wat'),
  watArun('thailand-wat-arun'),
  borobudur('indonesia-borobudur'),
  petra('jordan-petra'),
  giza('egypt-giza'),
  cappadocia('turkey-cappadocia'),
  eiffelTower('france-eiffel'),
  colosseum('italy-colosseum'),
  westminster('uk-westminster'),
  sagradaFamilia('spain-sagrada-familia'),
  tableMountain('south-africa-table-mountain'),
  machuPicchu('peru-machu-picchu'),
  rio('brazil-rio'),
  statueOfLiberty('usa-liberty'),
  lakeLouise('canada-lake-louise'),
  sydneyOperaHouse('australia-sydney');

  const LvHomeBanner(this.file);
  final String file;

  String get asset => 'assets/s1/home_banners/$file.webp';

  /// Called once by the app state, rather than each time the home page builds.
  static LvHomeBanner pick({Random? random}) {
    return values[(random ?? Random()).nextInt(values.length)];
  }
}

class LvHomeBannerImage extends StatelessWidget {
  const LvHomeBannerImage(this.banner, {super.key});
  final LvHomeBanner banner;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(16),
    child: AspectRatio(
      aspectRatio: 2,
      child: Image.asset(
        banner.asset,
        width: double.infinity,
        fit: BoxFit.cover,
        // Keep pencil detail clear on low-DPI screens without decoding every banner.
        cacheWidth:
            (MediaQuery.sizeOf(context).width *
                    MediaQuery.devicePixelRatioOf(context))
                .ceil()
                .clamp(768, 1774)
                .toInt(),
        filterQuality: FilterQuality.medium,
        excludeFromSemantics: true,
      ),
    ),
  );
}
