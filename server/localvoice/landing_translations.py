"""LP translations of three selected v1 DB stories. JA/EN come directly from the DB.

These editorial translations are deliberately version-pinned; they never alter the source records.
"""


def translated(title, body):
    return {'title': title, 'body': body, 'short': body, 'speech': body}


SELECTIONS = [
    {'key': 'curated:miyajima:torii-stands-by-weight', 'slug': 'torii', 'version': 'v1', 'icon': 'architecture',
     'places': dict(ja='広島・宮島', en='Miyajima, Hiroshima', zh='广岛·宫岛', ko='히로시마 · 미야지마', es='Miyajima, Hiroshima', fr='Miyajima, Hiroshima'),
     'translations': {
         'zh': translated('大鸟居竟然靠自己的重量站立', '严岛神社的大鸟居立在海中。它的柱子深埋在海底吗？还是另有支撑？答案是：通过在顶部横梁内填入石块等方式增加重量，让鸟居靠自身重量站立。主柱用的是巨大的天然樟树木。下次来到附近，记住这个小秘密：它立在海上，依靠的却是自己的重量。'),
         'ko': translated('큰 도리이는 자신의 무게로 서 있다', '바다에 서 있는 이쓰쿠시마 신사의 큰 도리이. 기둥이 바닷속 깊이 박혀 있을까요? 아니면 다른 방법으로 지탱할까요? 위쪽 가로대 안에 돌을 채우는 등 무게를 늘려, 도리이 자체의 무게로 서 있게 한 구조입니다. 주기둥에는 거대한 천연 녹나무를 사용했습니다. 다음에 이 근처를 지날 때 기억해 보세요. 바다 위에서 의지하는 것은 자신의 무게입니다.'),
         'es': translated('El gran torii se sostiene por su propio peso', 'El gran torii del santuario de Itsukushima se alza en el mar. ¿Sus pilares están enterrados en el fondo, o se sostiene de otra manera? La respuesta está arriba: se introducen piedras en la viga superior para darle peso, y la puerta se mantiene en pie por su propio peso. Los pilares principales son enormes troncos naturales de alcanforero. La próxima vez que pases cerca, recuerda: en medio del mar, su apoyo es su propio peso.'),
         'fr': translated('Le grand torii tient par son propre poids', 'Le grand torii du sanctuaire d’Itsukushima se dresse dans la mer. Ses piliers sont-ils profondément enfouis dans le fond marin ? Ou tient-il autrement ? Des pierres placées dans la poutre supérieure alourdissent la porte, qui tient debout par son propre poids. Ses piliers principaux sont d’énormes troncs naturels de camphrier. La prochaine fois que vous passerez à proximité, rappelez-vous : au milieu de la mer, il compte sur son propre poids.'),
     }},
    {'key': 'curated:nara:daibutsuden-narrower', 'slug': 'buddha-hall', 'version': 'v1', 'icon': 'history-topic',
     'places': dict(ja='奈良・東大寺', en='Tōdai-ji, Nara', zh='奈良·东大寺', ko='나라 · 도다이지', es='Tōdai-ji, Nara', fr='Tōdai-ji, Nara'),
     'translations': {
         'zh': translated('大佛殿缩小了，却仍是世界最大级别', '你可能以为大佛殿一直保持着最初的规模，其实并不是这样。它在战乱中两次被烧毁，现在的建筑是在江户时代重建的。由于材料不足等原因，正面宽度比最初缩小了约三成。即便如此，它仍是世界上规模最大的木建筑之一。下次经过大佛殿，记住这句话：缩小了，却依旧巨大。'),
         'ko': translated('줄어들었는데도 세계 최대급, 대불전', '대불전이 처음 지어진 크기를 그대로 이어 왔다고 생각하기 쉽지만, 사실은 그렇지 않습니다. 전란으로 두 번 불탔고, 지금 건물은 에도 시대에 다시 지었습니다. 자재 부족 등의 이유로 정면 폭은 창건 당시보다 약 30퍼센트 줄었다고 합니다. 그래도 세계에서 가장 큰 목조 건축물 중 하나입니다. 다음에 대불전 곁을 지날 때 기억해 보세요. 줄어들었는데도 세계 최대급입니다.'),
         'es': translated('Más pequeño, pero todavía entre los mayores', 'Es fácil pensar que el Salón del Gran Buda conserva su tamaño original. Pero no es así. Tras arder dos veces durante guerras, fue reconstruido en el período Edo. Por falta de materiales, entre otros motivos, su fachada quedó aproximadamente un treinta por ciento más estrecha que la original. Aun así, sigue siendo uno de los edificios de madera más grandes del mundo. La próxima vez que pases junto a él, recuerda: más pequeño, pero todavía entre los mayores.'),
         'fr': translated('Plus petit, mais toujours parmi les plus grands', 'On pourrait croire que la salle du Grand Bouddha a conservé ses dimensions d’origine. Ce n’est pourtant pas le cas. Après deux incendies lors de guerres, elle a été reconstruite à l’époque d’Edo. Le manque de matériaux, notamment, a réduit sa façade d’environ trente pour cent. Elle reste néanmoins l’un des plus grands bâtiments en bois du monde. La prochaine fois que vous passerez près de cette salle, rappelez-vous : plus petite, mais toujours immense.'),
     }},
    {'key': 'gen:xn764e:b636e2f0af00', 'slug': 'waste-heat', 'version': 'v1', 'icon': 'nature',
     'places': dict(ja='神奈川・堤根', en='Tsutsumine, Kanagawa', zh='神奈川·堤根', ko='가나가와 · 쓰쓰미네', es='Tsutsumine, Kanagawa', fr='Tsutsumine, Kanagawa'),
     'translations': {
         'zh': translated('垃圾焚烧的热量，还温暖了泳池', '垃圾处理设施把垃圾烧完，工作就结束了吗？堤根的热量还有下一站。停运前的处理中心有两千千瓦的发电设备，也有向温水游泳池等设施输送蒸汽的设备。中心于二〇二四年三月底停运。二〇二六年五月，川崎市公布了拆除老旧设施、建设新焚烧处理设施的方针。在堤根，垃圾的热量曾变成电力，也连到了泳池的温水。'),
         'ko': translated('쓰레기의 열이 수영장 온수까지 이어졌다', '쓰레기 처리 시설은 태우고 나면 끝일까요? 쓰쓰미네에서는 그 열에 다음 행선지가 있었습니다. 가동 중단 전 센터에는 2천 킬로와트 발전 설비가 있었고, 온수 수영장 등에 증기를 보내는 설비도 있었습니다. 센터는 2024년 3월 말에 가동을 중단했습니다. 2026년 5월 가와사키시는 노후 시설을 철거하고 새로운 소각 처리 시설을 정비할 방침을 발표했습니다. 이곳에서는 쓰레기의 열이 전기와 수영장의 온수로 이어졌습니다.'),
         'es': translated('El calor de la basura también calentaba una piscina', 'Una planta de residuos quema basura, y ya está. ¿O no? Antes de suspender su actividad, el centro de Tsutsumine tenía equipos de generación de dos mil kilovatios y suministraba vapor a instalaciones como una piscina climatizada. El centro dejó de funcionar a finales de marzo de 2024. En mayo de 2026 Kawasaki anunció su intención de demoler la instalación envejecida y construir una nueva planta de incineración. Aquí, el calor de la basura producía electricidad y también agua caliente para una piscina.'),
         'fr': translated('La chaleur des déchets réchauffait aussi une piscine', 'Une usine de traitement des déchets les brûle, puis tout s’arrête ? À Tsutsumine, la chaleur avait une autre destination. Avant sa suspension, le centre disposait d’équipements de production électrique de deux mille kilowatts et fournissait de la vapeur à des installations dont une piscine chauffée. Il a été suspendu fin mars 2024. En mai 2026, Kawasaki a annoncé son intention de démolir le site vieillissant et de construire une nouvelle usine d’incinération. Ici, la chaleur des déchets donnait de l’électricité et de l’eau chaude pour une piscine.'),
     }},
]
