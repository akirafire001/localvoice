"""Draft curated stories for the PoC regions (宮島・広島・尾道・奈良).

These are DRAFTS written from well-known public information. Before the real trip a person must check
each claim against its source and the reading of place names (content-quality-policy §2, §4).
Until then they carry review_status=unreviewed and story_quality.reviewer=draft.

Load with:  flask --app localvoice seed
"""

W = "https://ja.wikipedia.org/wiki/"
WE = "https://en.wikipedia.org/wiki/"

ITEMS = [
    # ------------------------------------------------------------ 宮島
    {
        "key": "miyajima:torii-stands-by-weight",
        "title": "大鳥居は自分の重さで立っている", "title_en": "The great torii stands by its own weight",
        "category": "architecture", "lat": 34.2970, "lon": 132.3187, "radius_m": 400,
        "fact_type": "verified_fact",
        "short_ja": "厳島神社の大鳥居は、海底に深く埋められているわけではなく、自らの重さで立っています。",
        "body_ja": "厳島神社の大鳥居は、海底に柱を深く埋め込んで固定しているわけではありません。笠木の内部に石を詰めるなどして重くし、自らの重さで立つ構造になっています。主柱には巨大なクスノキの自然木が使われています。",
        "short_en": "Itsukushima's great torii is not buried deep in the seabed; it stands by its own weight.",
        "body_en": "The great torii of Itsukushima Shrine is not anchored deep in the seabed. Its top beam is weighted, for example with stones packed inside, so that the gate stands by its own weight. The main pillars are made from huge natural camphor trees.",
        "claims": [
            ("大鳥居は海底に埋められておらず、自らの重さで立っている。", "The torii is not buried in the seabed and stands by its own weight."),
            ("主柱にはクスノキの自然木が使われている。", "The main pillars are natural camphor wood."),
        ],
        "sources": [("厳島神社", W + "厳島神社"), ("Itsukushima Shrine", WE + "Itsukushima_Shrine")],
        "content_kind": "local_trivia", "why_here": "大鳥居の近くで構造の意外さを伝える",
        "interest_hook": "海に立つ鳥居が埋められていないという意外性", "interestingness": 0.9, "novelty": 0.7,
    },
    {
        "key": "miyajima:shrine-over-sea",
        "title": "社殿が海の上にある理由", "title_en": "Why the shrine stands over the sea",
        "category": "culture", "lat": 34.2959, "lon": 132.3199, "radius_m": 300,
        "fact_type": "tradition",
        "short_ja": "島そのものが神として信仰されていたため、土地を傷つけないよう潮の満ち引きする場所に社殿を建てたと伝えられています。",
        "body_ja": "宮島は古くから島全体が神として信仰されてきました。そのため島の土地を切り開くことをはばかり、潮が満ち引きする浜に社殿を建てたと伝えられています。満潮時には社殿が海に浮かんでいるように見えることで知られています。",
        "short_en": "The whole island was revered as a god, so the shrine is said to have been built over the tidal flats to avoid harming the land.",
        "body_en": "Miyajima itself has long been worshipped as a deity. It is said that, to avoid cutting into the sacred land, the shrine was built on the tidal flats where the sea comes and goes. At high tide the buildings are known for appearing to float on the water.",
        "claims": [
            ("宮島は島全体が神として信仰されてきた。", "The whole island has been worshipped as a deity."),
            ("島の土地を傷つけないよう、潮が満ち引きする浜に社殿を建てたと伝えられる。", "Tradition says the shrine was built on tidal flats to avoid harming the land."),
        ],
        "sources": [("厳島神社", W + "厳島神社")],
        "content_kind": "origin", "why_here": "社殿のそばで建築位置の理由を伝える",
        "interest_hook": "海に建てた理由が島への信仰にある", "interestingness": 0.85, "novelty": 0.6,
    },
    {
        "key": "miyajima:shamoji",
        "title": "宮島しゃもじの始まり", "title_en": "How the Miyajima rice paddle began",
        "category": "industry", "lat": 34.2985, "lon": 132.3215, "radius_m": 600,
        "fact_type": "tradition",
        "short_ja": "宮島はしゃもじの名産地。江戸時代の僧・誓真が、弁財天の琵琶の形から考案して島の人に作り方を教えたと伝えられています。",
        "body_ja": "宮島は杓子、いわゆるしゃもじの名産地として知られています。江戸時代に島に住んだ僧・誓真が、弁財天の持つ琵琶の形をヒントに杓子を考案し、島の人々に作り方を教えたのが始まりと伝えられています。「敵をめしとる」に通じる縁起物としても親しまれてきました。",
        "short_en": "Miyajima is famous for rice paddles. Legend credits an Edo-period monk, Seishin, who modelled them on the biwa lute of the goddess Benzaiten.",
        "body_en": "Miyajima is known for its shamoji, wooden rice paddles. Tradition says an Edo-period monk named Seishin designed the paddle after the shape of the biwa lute held by the goddess Benzaiten and taught islanders to make it. Because 'scooping up rice' sounds like 'capturing the enemy' in Japanese, it also became a good-luck charm.",
        "claims": [
            ("宮島は杓子（しゃもじ）の名産地である。", "Miyajima is known for producing rice paddles."),
            ("江戸時代の僧・誓真が琵琶の形から杓子を考案したと伝えられる。", "Tradition credits the monk Seishin with designing the paddle after a biwa."),
        ],
        "sources": [("宮島杓子", W + "宮島杓子")],
        "content_kind": "anecdote", "why_here": "表参道商店街で土産物の背景を伝える",
        "interest_hook": "身近な台所道具の由来が僧と琵琶にある", "interestingness": 0.8, "novelty": 0.8,
    },
    {
        "key": "miyajima:momiji-manju",
        "title": "もみじ饅頭と伊藤博文の逸話", "title_en": "Momiji manju and the Ito Hirobumi anecdote",
        "category": "food", "lat": 34.2990, "lon": 132.3220, "radius_m": 800,
        "fact_type": "legend",
        "short_ja": "もみじ饅頭は明治時代末に宮島で生まれた菓子。伊藤博文が茶屋の娘の手を「紅葉のよう」と言ったことがきっかけという逸話が伝わります。",
        "body_ja": "宮島名物のもみじ饅頭は、明治時代の末に宮島の菓子職人・高津常助が考案したとされます。伊藤博文が紅葉谷の茶屋で働く娘の手を見て「紅葉のようなかわいらしい手だ」と言ったことが着想のきっかけになった、という逸話が地元に伝わっていますが、確かな記録ではありません。",
        "short_en": "Momiji manju were created on Miyajima in the late Meiji era. A local tale links them to Ito Hirobumi praising a tea-house girl's 'maple-leaf hands'.",
        "body_en": "Miyajima's famous maple-leaf cakes are said to have been created in the late Meiji era by confectioner Takatsu Tsunesuke. A local anecdote says the idea came when statesman Ito Hirobumi remarked that a tea-house girl's hands were as lovely as maple leaves, though this is a tale rather than a documented fact.",
        "claims": [
            ("もみじ饅頭は明治時代末に宮島の高津常助が考案したとされる。", "Momiji manju are said to have been created by Takatsu Tsunesuke in the late Meiji era."),
            ("伊藤博文の「紅葉のような手」の発言がきっかけという逸話が伝わる。", "An anecdote links the idea to Ito Hirobumi's remark about maple-leaf hands."),
        ],
        "sources": [("もみじ饅頭", W + "もみじ饅頭")],
        "content_kind": "anecdote", "why_here": "宮島の名物菓子の発祥地で伝える",
        "interest_hook": "有名な菓子と首相の逸話", "interestingness": 0.8, "novelty": 0.5,
    },
    {
        "key": "miyajima:island-area",
        "title": "宮島の暮らしと神聖な島", "title_en": "Daily life on a sacred island",
        "category": "everyday_life", "lat": 34.2800, "lon": 132.3100, "radius_m": 4000, "scope": "area",
        "fact_type": "likely",
        "short_ja": "島全体が神聖とされてきた宮島では、古くから島内で出産や埋葬を避け、対岸の地で行う習わしがあったとされます。",
        "body_ja": "宮島は島そのものが信仰の対象とされてきたため、死や出産にまつわる「けがれ」を島に持ち込まない習わしがあったとされます。古くは島内に墓を設けず、対岸の地に葬ったといわれています。島の暮らしそのものが信仰と結びついてきたことがうかがえます。",
        "short_en": "Because the whole island was considered sacred, births and burials were traditionally kept off Miyajima and carried out on the mainland opposite.",
        "body_en": "Since the island itself has been an object of worship, there was a custom of keeping the impurity associated with death and childbirth away from it. In the past, graves were not made on the island and the dead were buried on the opposite shore. Everyday life here has long been tied to faith.",
        "claims": [
            ("宮島では古くから島内に墓を設けず、対岸の地に葬ったとされる。", "Traditionally no graves were made on the island; burials took place on the mainland."),
            ("死や出産のけがれを島に持ち込まない習わしがあったとされる。", "There was a custom of keeping the impurity of death and birth off the island."),
        ],
        "sources": [("厳島", W + "厳島")],
        "content_kind": "everyday_culture", "why_here": "宮島の島内全体で暮らしの背景を伝える",
        "interest_hook": "島に墓がないという身近な驚き", "interestingness": 0.85, "novelty": 0.85,
    },
    # ------------------------------------------------------------ 広島
    {
        "key": "hiroshima:dome-architect",
        "title": "原爆ドームを設計したのはチェコの建築家", "title_en": "A Czech architect designed the A-Bomb Dome",
        "category": "architecture", "lat": 34.3955, "lon": 132.4536, "radius_m": 300,
        "fact_type": "verified_fact",
        "short_ja": "原爆ドームは、もとは広島県産業奨励館。チェコの建築家ヤン・レツルの設計で1915年に完成した建物でした。",
        "body_ja": "原爆ドームは、もともと広島県の物産を展示・販売する広島県産業奨励館として建てられました。設計したのはチェコ出身の建築家ヤン・レツルで、1915年に完成しました。1945年8月6日の原爆で被爆し、骨組みを残した姿が保存されています。",
        "short_en": "The A-Bomb Dome was originally the Hiroshima Prefectural Industrial Promotion Hall, designed by Czech architect Jan Letzel and completed in 1915.",
        "body_en": "The A-Bomb Dome was built as the Hiroshima Prefectural Industrial Promotion Hall, a place to exhibit and sell local products. It was designed by Czech architect Jan Letzel and completed in 1915. Hit by the atomic bomb on 6 August 1945, its skeletal remains have been preserved.",
        "claims": [
            ("原爆ドームはもと広島県産業奨励館である。", "The dome was originally the Prefectural Industrial Promotion Hall."),
            ("チェコの建築家ヤン・レツルが設計し、1915年に完成した。", "It was designed by Czech architect Jan Letzel and completed in 1915."),
        ],
        "sources": [("原爆ドーム", W + "原爆ドーム"), ("Hiroshima Peace Memorial", WE + "Hiroshima_Peace_Memorial")],
        "content_kind": "anecdote", "why_here": "原爆ドームのそばで建物の元の姿を伝える",
        "interest_hook": "平和の象徴が元は物産館で、外国人建築家の設計", "interestingness": 0.85, "novelty": 0.7,
    },
    {
        "key": "hiroshima:name-origin",
        "title": "「広島」という地名の由来", "title_en": "Where the name 'Hiroshima' came from",
        "category": "culture", "lat": 34.4027, "lon": 132.4594, "radius_m": 1500,
        "fact_type": "tradition",
        "short_ja": "「広島」の名は、毛利輝元が築城の際、祖先の大江広元の「広」と案内役の福島元長の「島」を合わせたという説があります。",
        "body_ja": "広島という地名の由来には諸説あります。よく知られているのは、毛利輝元が広島城を築く際、毛利氏の祖先である大江広元の「広」と、この地を案内した福島元長の「島」を組み合わせたという説です。一方で、太田川の三角州に広い島があったことに由来するという見方もあります。",
        "short_en": "One theory says Mori Terumoto named Hiroshima by combining 'Hiro' from his ancestor Oe no Hiromoto and 'shima' from his local guide Fukushima Motonaga.",
        "body_en": "There are several theories about the name Hiroshima. A well-known one holds that when Mori Terumoto built Hiroshima Castle he combined 'Hiro' from his ancestor Oe no Hiromoto with 'shima' from Fukushima Motonaga, who guided him here. Another view links it to a broad island in the Ota River delta.",
        "claims": [
            ("毛利輝元が大江広元の「広」と福島元長の「島」を合わせたという説がある。", "One theory says Mori Terumoto combined the names of Oe no Hiromoto and Fukushima Motonaga."),
            ("太田川の三角州の広い島に由来するという見方もある。", "Another view links the name to a broad island in the delta."),
        ],
        "sources": [("広島市", W + "広島市"), ("広島城", W + "広島城")],
        "content_kind": "origin", "why_here": "広島城の周辺で地名の由来を伝える",
        "interest_hook": "毎日聞く地名に人名由来の説がある", "interestingness": 0.85, "novelty": 0.8,
    },
    {
        "key": "hiroshima:delta-rivers",
        "title": "川に囲まれた三角州の街", "title_en": "A city built on a river delta",
        "category": "nature", "lat": 34.3963, "lon": 132.4596, "radius_m": 5000, "scope": "area",
        "fact_type": "verified_fact",
        "short_ja": "広島の中心部は太田川がつくった三角州の上にあり、市街地をいくつもの川が流れています。橋が多いのはそのためです。",
        "body_ja": "広島市の中心部は、太田川が運んだ土砂でできた三角州の上に広がっています。市街地を何本もの川が分かれて流れているため、移動すると次々に橋を渡ることになります。広島城もこの三角州に築かれました。",
        "short_en": "Central Hiroshima sits on a delta formed by the Ota River, with several river channels running through town — hence all the bridges.",
        "body_en": "Central Hiroshima spreads over a delta built from sediment carried by the Ota River. Several channels split and flow through the city, so moving around you keep crossing bridges. Hiroshima Castle itself was built on this delta.",
        "claims": [
            ("広島市中心部は太田川の三角州の上にある。", "Central Hiroshima lies on the Ota River delta."),
            ("市街地を複数の川が流れている。", "Several river channels flow through the city."),
        ],
        "sources": [("太田川", W + "太田川"), ("広島市", W + "広島市")],
        "content_kind": "regional_background", "why_here": "広島市街のどこでも当てはまる地形の話",
        "interest_hook": "橋が多い理由が地形にある", "interestingness": 0.7, "novelty": 0.6,
    },
    {
        "key": "hiroshima:okonomiyaki",
        "title": "重ねて焼く広島のお好み焼き", "title_en": "Hiroshima's layered okonomiyaki",
        "category": "food", "lat": 34.3925, "lon": 132.4610, "radius_m": 3000, "scope": "area",
        "fact_type": "likely",
        "short_ja": "広島のお好み焼きは、生地を薄く焼いてキャベツや麺を重ねるのが特徴。戦前の「一銭洋食」が原型といわれます。",
        "body_ja": "広島風お好み焼きは、具材を混ぜずに、薄く焼いた生地の上にキャベツ、豚肉、そばやうどんの麺、卵を重ねて焼くのが特徴です。原型は戦前に駄菓子屋などで売られた「一銭洋食」といわれ、戦後の広島で今の形に発展したとされます。",
        "short_en": "Hiroshima okonomiyaki is layered rather than mixed, with cabbage and noodles on a thin crepe. Its ancestor is said to be the pre-war 'issen yoshoku' snack.",
        "body_en": "Hiroshima-style okonomiyaki is not mixed: cabbage, pork, soba or udon noodles and egg are layered on a thin crepe and cooked. Its origin is said to be 'issen yoshoku', a cheap pre-war snack, and it developed into today's form in post-war Hiroshima.",
        "claims": [
            ("広島風お好み焼きは具材を重ねて焼く。", "Hiroshima-style okonomiyaki is layered."),
            ("原型は一銭洋食といわれ、戦後の広島で発展したとされる。", "Its origin is said to be issen yoshoku, developing in post-war Hiroshima."),
        ],
        "sources": [("お好み焼き", W + "お好み焼き")],
        "content_kind": "everyday_culture", "why_here": "広島市街の食文化",
        "interest_hook": "大阪風との違いと戦後の歴史", "interestingness": 0.7, "novelty": 0.4,
        "season_months": None,
    },
    {
        "key": "hiroshima:hibaku-tram",
        "title": "今も走る被爆電車", "title_en": "Trams that survived the bomb still run",
        "category": "industry", "lat": 34.3934, "lon": 132.4572, "radius_m": 2500, "scope": "area",
        "fact_type": "verified_fact",
        "short_ja": "広島の路面電車には、原爆に遭いながら修理されて今も走る「被爆電車」があります。",
        "body_ja": "広島電鉄の路面電車は、原爆投下からわずか3日後に一部区間で運行を再開しました。被爆した車両の中には修理されて今も現役で走るものがあり、「被爆電車」と呼ばれています。",
        "short_en": "Some of Hiroshima's trams survived the atomic bomb, were repaired, and still run today.",
        "body_en": "Hiroshima Electric Railway restarted part of its tram service just three days after the atomic bombing. Several trams that were damaged in the bombing were repaired and are still in service, known as 'hibaku densha'.",
        "claims": [
            ("広島電鉄は原爆投下の3日後に一部区間で運行を再開した。", "Hiroden resumed partial service three days after the bombing."),
            ("被爆した車両の一部は修理されて今も走っている。", "Some damaged trams were repaired and still operate."),
        ],
        "sources": [("広島電鉄", W + "広島電鉄"), ("Hiroshima Electric Railway", WE + "Hiroshima_Electric_Railway")],
        "content_kind": "anecdote", "why_here": "市内電車の通りで伝える",
        "interest_hook": "街の交通そのものが歴史の生き証人", "interestingness": 0.85, "novelty": 0.75,
    },
    # ------------------------------------------------------------ 尾道
    {
        "key": "onomichi:suido",
        "title": "川のように見える海、尾道水道", "title_en": "Onomichi Channel, a sea that looks like a river",
        "category": "nature", "lat": 34.4065, "lon": 133.2010, "radius_m": 1200,
        "fact_type": "verified_fact",
        "short_ja": "尾道と向島の間の尾道水道は幅数百メートルほどの海峡。対岸へは今も渡船が日常の足になっています。",
        "body_ja": "尾道市街と向島の間を流れる尾道水道は、幅がおよそ200〜300メートルほどの狭い海峡で、川のようにも感じられます。古くから天然の良港として栄え、今も複数の渡船が数分で対岸と行き来し、通勤や通学の足になっています。",
        "short_en": "The Onomichi Channel between the town and Mukaishima is only a few hundred metres wide, and small ferries are still an everyday commute.",
        "body_en": "The Onomichi Channel separating the town from Mukaishima island is only around 200-300 metres wide and feels almost like a river. It has long served as a natural harbour, and several small ferries still cross in a few minutes, carrying commuters and students.",
        "claims": [
            ("尾道水道は尾道と向島の間の狭い海峡である。", "The Onomichi Channel is a narrow strait between Onomichi and Mukaishima."),
            ("渡船が対岸と行き来し日常の交通になっている。", "Ferries cross the channel as everyday transport."),
        ],
        "sources": [("尾道水道", W + "尾道水道"), ("向島 (広島県)", W + "向島_(広島県)")],
        "content_kind": "regional_background", "why_here": "尾道水道沿いで伝える",
        "interest_hook": "海峡なのに川のよう、渡船が通勤の足", "interestingness": 0.75, "novelty": 0.7,
    },
    {
        "key": "onomichi:ramen",
        "title": "尾道ラーメンの背脂", "title_en": "The pork fat in Onomichi ramen",
        "category": "food", "lat": 34.4085, "lon": 133.2050, "radius_m": 2500, "scope": "area",
        "fact_type": "likely",
        "short_ja": "尾道ラーメンは、瀬戸内の小魚でだしをとった醤油スープに、豚の背脂のミンチを浮かべるのが特徴です。",
        "body_ja": "尾道ラーメンは、鶏ガラに瀬戸内でとれる小魚のだしを合わせた醤油スープに、細かくした豚の背脂を浮かべるのが特徴とされます。平たい麺もよく使われます。港町ならではの魚のだしが、この土地のラーメンを形づくっています。",
        "short_en": "Onomichi ramen combines a soy broth with stock from small Seto Inland Sea fish, topped with minced pork back fat.",
        "body_en": "Onomichi ramen is characterised by a soy-sauce broth of chicken bones and stock from small fish caught in the Seto Inland Sea, topped with bits of pork back fat, often with flat noodles. The fishing-port setting shapes the local bowl.",
        "claims": [
            ("尾道ラーメンは瀬戸内の小魚のだしを使った醤油スープが特徴とされる。", "Onomichi ramen features a soy broth with small-fish stock."),
            ("豚の背脂のミンチを浮かべる。", "It is topped with minced pork back fat."),
        ],
        "sources": [("尾道ラーメン", W + "尾道ラーメン")],
        "content_kind": "everyday_culture", "why_here": "尾道市街の食文化",
        "interest_hook": "港町の魚だしがラーメンに", "interestingness": 0.65, "novelty": 0.5,
    },
    {
        "key": "onomichi:tama-no-iwa",
        "title": "千光寺の玉の岩伝説", "title_en": "The legend of Senkoji's Tama-no-iwa rock",
        "category": "culture", "lat": 34.4097, "lon": 133.1980, "radius_m": 400,
        "fact_type": "legend",
        "short_ja": "千光寺の「玉の岩」には、かつて岩の上の宝玉が夜ごと光り、海を照らしたという伝説があります。尾道の古い呼び名「玉の浦」の由来ともいわれます。",
        "body_ja": "千光寺山の「玉の岩」には、昔、岩の上に光る宝玉があり、夜になると海を照らしたという伝説が残っています。この玉にちなんで、尾道はかつて「玉の浦」とも呼ばれたといわれます。あくまで伝説ですが、港町と灯りのイメージを今に伝えています。",
        "short_en": "Legend says a jewel atop Senkoji's Tama-no-iwa rock once shone over the sea at night, giving Onomichi its old poetic name 'Tama-no-ura'.",
        "body_en": "A legend tells of a glowing jewel on top of the Tama-no-iwa rock at Senkoji that lit up the sea at night. Onomichi is said to have been called 'Tama-no-ura', the Bay of the Jewel, after it. It is only a legend, but it links the port with the image of a guiding light.",
        "claims": [
            ("玉の岩には宝玉が夜に光って海を照らしたという伝説がある。", "Legend says a jewel on the rock lit the sea at night."),
            ("尾道はかつて「玉の浦」と呼ばれたといわれる。", "Onomichi is said to have been called Tama-no-ura."),
        ],
        "sources": [("千光寺 (尾道市)", W + "千光寺_(尾道市)")],
        "content_kind": "anecdote", "why_here": "千光寺の近くで伝える",
        "interest_hook": "地名につながる光る石の伝説", "interestingness": 0.8, "novelty": 0.8,
    },
    {
        "key": "onomichi:temples-slopes",
        "title": "坂と寺の町になった理由", "title_en": "Why Onomichi is a town of slopes and temples",
        "category": "history", "lat": 34.4090, "lon": 133.2000, "radius_m": 1500,
        "fact_type": "likely",
        "short_ja": "尾道は中世から港町として栄え、豊かな商人が寺を寄進したため、山と海に挟まれた狭い斜面に多くの寺が並んでいます。",
        "body_ja": "尾道は中世から瀬戸内海の港町として栄え、豪商たちが寺院を寄進・保護してきました。山が海に迫る狭い土地のため、寺や家々は斜面に建ち並び、坂道と路地の町並みができあがりました。今も古寺をめぐる散策路が整えられています。",
        "short_en": "Wealthy merchants of this medieval port endowed many temples, and with the hills pressing on the sea, temples and houses climbed the slopes.",
        "body_en": "Onomichi prospered as a Seto Inland Sea port from the medieval period, and rich merchants endowed and supported its temples. With mountains crowding the shore, temples and homes were built on the slopes, creating the town of steps and alleys you walk today, now linked by a temple-walking route.",
        "claims": [
            ("尾道は中世から港町として栄えた。", "Onomichi prospered as a port from medieval times."),
            ("商人が寺院を寄進し、斜面に多くの寺が建ち並んだ。", "Merchants endowed temples, which line the slopes."),
        ],
        "sources": [("尾道市", W + "尾道市")],
        "content_kind": "regional_background", "why_here": "尾道の坂の町並みで伝える",
        "interest_hook": "坂と寺の多さが港の繁栄と地形の結果", "interestingness": 0.75, "novelty": 0.6,
    },
    # ------------------------------------------------------------ 奈良
    {
        "key": "nara:deer-messengers",
        "title": "鹿が神の使いとされる理由", "title_en": "Why Nara's deer are sacred messengers",
        "category": "culture", "lat": 34.6851, "lon": 135.8430, "radius_m": 1500,
        "fact_type": "tradition",
        "short_ja": "奈良の鹿は、春日大社の神様が白い鹿に乗って鹿島からやって来たという伝承から、神の使いとして大切にされてきました。",
        "body_ja": "春日大社に祀られる武甕槌命（たけみかづちのみこと）は、常陸国の鹿島から白い鹿に乗って御蓋山にやって来たと伝えられています。そのため奈良の鹿は神の使いとして大切に守られてきました。現在、奈良の鹿は国の天然記念物に指定されています。",
        "short_en": "Nara's deer are cherished as divine messengers because Kasuga Taisha's god is said to have arrived riding a white deer from Kashima.",
        "body_en": "Takemikazuchi, enshrined at Kasuga Taisha, is said to have travelled from Kashima in Hitachi Province riding a white deer. Ever since, Nara's deer have been protected as messengers of the gods, and today they are designated a national natural monument.",
        "claims": [
            ("春日大社の祭神が白い鹿に乗ってやって来たと伝えられる。", "Kasuga's deity is said to have arrived on a white deer."),
            ("奈良の鹿は国の天然記念物に指定されている。", "Nara's deer are a designated national natural monument."),
        ],
        "sources": [("奈良公園", W + "奈良公園"), ("春日大社", W + "春日大社")],
        "content_kind": "origin", "why_here": "奈良公園で鹿の背景を伝える",
        "interest_hook": "鹿が守られる理由が神話にある", "interestingness": 0.85, "novelty": 0.5,
    },
    {
        "key": "nara:daibutsuden-narrower",
        "title": "大仏殿は昔より狭くなった", "title_en": "The Great Buddha Hall used to be wider",
        "category": "architecture", "lat": 34.6890, "lon": 135.8398, "radius_m": 500,
        "fact_type": "verified_fact",
        "short_ja": "今の東大寺大仏殿は江戸時代の再建で、奈良時代の創建時より横幅がおよそ3割狭くなっています。それでも世界最大級の木造建築です。",
        "body_ja": "東大寺の大仏殿は戦乱で二度焼失し、現在の建物は江戸時代に再建されたものです。資材の不足などから、正面の幅は創建当初より約3割狭くなりました。それでも世界最大級の木造建築として知られています。",
        "short_en": "Todaiji's current Great Buddha Hall is an Edo-period rebuild about 30% narrower than the original — yet still among the largest wooden buildings in the world.",
        "body_en": "Todaiji's Great Buddha Hall burned down twice in wars, and the current building is an Edo-period reconstruction. Partly because of material shortages its front is about 30 percent narrower than the original. Even so, it remains one of the largest wooden buildings in the world.",
        "claims": [
            ("現在の大仏殿は江戸時代の再建である。", "The current hall is an Edo-period reconstruction."),
            ("正面の幅は創建時より約3割狭い。", "Its width is about 30 percent narrower than the original."),
            ("世界最大級の木造建築である。", "It is one of the largest wooden buildings in the world."),
        ],
        "sources": [("東大寺", W + "東大寺"), ("Tōdai-ji", WE + "T%C5%8Ddai-ji")],
        "content_kind": "local_trivia", "why_here": "大仏殿の周辺で伝える",
        "interest_hook": "巨大な建物が実は縮小版", "interestingness": 0.9, "novelty": 0.75,
    },
    {
        "key": "nara:narazuke",
        "title": "奈良漬の名前の由来", "title_en": "Why it's called Narazuke",
        "category": "food", "lat": 34.6850, "lon": 135.8320, "radius_m": 4000, "scope": "area",
        "fact_type": "likely",
        "short_ja": "奈良漬は、白瓜などを酒粕に何度も漬け替えて作る漬物。奈良が酒造りの盛んな土地だったことと結びついています。",
        "body_ja": "奈良漬は、白瓜やきゅうりなどの野菜を酒粕に漬け、何度も新しい粕に漬け替えて熟成させる漬物です。奈良は古くから酒造りの盛んな土地で、その酒粕を使った漬物が奈良の名とともに広まったとされます。",
        "short_en": "Narazuke are vegetables pickled repeatedly in sake lees — tied to Nara's long history of sake brewing.",
        "body_en": "Narazuke are vegetables such as white gourd pickled in sake lees and moved into fresh lees several times as they mature. Nara has a long history of sake brewing, and pickles made with its lees spread under Nara's name.",
        "claims": [
            ("奈良漬は野菜を酒粕に漬け替えて作る漬物である。", "Narazuke are vegetables pickled in sake lees."),
            ("奈良は古くから酒造りの盛んな土地である。", "Nara has a long history of sake brewing."),
        ],
        "sources": [("奈良漬", W + "奈良漬")],
        "content_kind": "everyday_culture", "why_here": "奈良市街の食文化",
        "interest_hook": "名物の名前と酒造りのつながり", "interestingness": 0.65, "novelty": 0.6,
    },
    {
        "key": "nara:shika-senbei",
        "title": "鹿せんべいに砂糖は入っていない", "title_en": "Deer crackers contain no sugar",
        "category": "everyday_life", "lat": 34.6845, "lon": 135.8440, "radius_m": 1200,
        "fact_type": "likely",
        "short_ja": "奈良公園の鹿せんべいは、鹿の健康を考えて米ぬかと小麦粉で作られ、砂糖などは使われていません。人が食べても味はほとんどしないそうです。",
        "body_ja": "奈良公園で売られている鹿せんべいは、鹿の体に配慮して米ぬかと小麦粉を主な原料に作られており、砂糖や調味料は使われていないとされます。売り上げの一部は鹿の保護活動にも役立てられています。",
        "short_en": "Nara's deer crackers are made mainly from rice bran and wheat flour with no sugar, out of concern for the deer's health.",
        "body_en": "The shika senbei sold in Nara Park are made mainly of rice bran and wheat flour, reportedly with no sugar or seasoning, out of consideration for the deer's health. Part of the proceeds supports deer protection.",
        "claims": [
            ("鹿せんべいは米ぬかと小麦粉を主な原料とし、砂糖は使われていないとされる。", "Deer crackers are made of rice bran and flour without sugar."),
            ("売り上げの一部は鹿の保護に使われる。", "Part of the proceeds supports deer protection."),
        ],
        "sources": [("鹿せんべい", W + "鹿せんべい")],
        "content_kind": "local_trivia", "why_here": "奈良公園で鹿せんべいの話",
        "interest_hook": "誰もが買うせんべいの意外な中身", "interestingness": 0.7, "novelty": 0.8,
    },
]


def load(db):
    from sqlalchemy import select

    from ..models import KnowledgeClaim, KnowledgeItem, KnowledgeSource
    from ..util import now

    created = updated = 0
    for d in ITEMS:
        key = f"curated:{d['key']}"
        item = db.execute(select(KnowledgeItem).where(KnowledgeItem.canonical_key == key)).scalar_one_or_none()
        if item is None:
            item = KnowledgeItem(canonical_key=key)
            db.add(item)
            created += 1
        else:
            updated += 1
            for s in list(item.sources):
                db.delete(s)
            for c in list(item.claims):
                db.delete(c)
            db.flush()
        item.title, item.title_en, item.category = d["title"], d["title_en"], d["category"]
        item.short_ja, item.body_ja, item.short_en, item.body_en = d["short_ja"], d["body_ja"], d["short_en"], d["body_en"]
        item.position = f"SRID=4326;POINT({d['lon']} {d['lat']})"
        item.radius_m = d["radius_m"]
        item.fact_type = d["fact_type"]
        item.confidence_level = "medium"
        item.interestingness = d.get("interestingness", 0.7)
        item.novelty = d.get("novelty", 0.6)
        item.origin, item.review_status = "curated", "unreviewed"
        told = item.metadata_json or {}
        item.metadata_json = {
            "scope": d.get("scope", "point"),
            "topics": [d["key"].split(":")[0]],
            "story_quality": {
                "content_kind": d["content_kind"], "why_here": d["why_here"], "interest_hook": d["interest_hook"],
                "present_connection": None, "auto_eligible": True, "hold_reason": None,
                "reviewer": "draft", "reviewed_at": None, "review_version": "draft-1",
            },
            "speech": {"ja": d["short_ja"], "en": d["short_en"]},
            **({"season_months": d["season_months"]} if d.get("season_months") else {}),
            # keep a spoken version written by `flask rewrite-stories` across re-seeding
            **({k: told[k] for k in ("speech", "storytelling")} if told.get("storytelling") else {}),
        }
        db.flush()
        src_ids = []
        for title, url in d["sources"]:
            s = KnowledgeSource(knowledge_item_id=item.id, url=url, title=title,
                                publisher="Wikipedia" if "wikipedia" in url else None,
                                retrieved_at=now(), source_type="wikipedia", reliability_score=0.6,
                                license_info="CC BY-SA 4.0 (Wikipedia)")
            db.add(s)
            db.flush()
            src_ids.append(s.id)
        for ja, en in d["claims"]:
            db.add(KnowledgeClaim(knowledge_item_id=item.id, claim_text_ja=ja, claim_text_en=en, source_ids=src_ids))
    return created, updated
