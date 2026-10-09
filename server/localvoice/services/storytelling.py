"""How LocalVoice stories are told: story types, eras and the storytelling technique catalogue.

The catalogue follows /mnt/project-files/notes/storytelling-techniques-v0.1.md (agreed 2026-10-08). Codes are
the catalogue's ids; B7 (cliffhanger to the next spot) and D4 (quiz answered minutes later) are left out because
they would tie one story's timing to the next. Generation writes a spoken version of each story with these
techniques; selection rotates them so consecutive stories do not sound alike.
"""

STORY_TYPES = {
    "landform_trace": "today's roads, rails, slopes or blocks trace an old river, levee, shore or field",
    "boundary_quirk": "a boundary, fare zone, address or name that does not match (\"X, and yet Y\")",
    "why_here": "why a station, factory, market, inn or temple is at this very spot",
    "lost_trace": "something that is gone (hot spring, cinema street, factory, yard) and what is left of it",
    "spread_from_here": "something born here, or local material that went somewhere famous",
    "person_moment": "what a named person did here, as a scene",
    "past_life": "how people here used to live: water, food, work, transport",
    "body_number": "a length, height or size turned into something the listener can feel",
    "town_today": "festivals, seasonal events and local habits of today",
    "place_name": "a place-name origin, only when it has a payoff",
    "famous_person": "a well-known or locally important person with a concrete tie to this place",
    "local_tip": "an insider tip (a spot, the best time or conditions, how to order or eat, what to buy, a craft to watch) with the reason behind it",
    "custom_manner": "a manner, taboo or habit of the people here and why it exists",
}

# Keys follow Japanese periods; outside Japan an era is picked by its years (in brackets).
ERAS = {
    "prehistoric": "geology and deep time",
    "jomon_kofun": "Jomon, Yayoi and Kofun (before 600)",
    "ancient": "ancient (Asuka to Heian; 600-1185)",
    "medieval": "medieval (Kamakura, Muromachi; 1185-1467)",
    "sengoku": "Sengoku (1467-1603)",
    "edo": "Edo (1603-1868)",
    "meiji_prewar": "Meiji to pre-war Showa (1868-1936)",
    "war_postwar": "war and post-war (1937-1988)",
    "heisei_later": "Heisei and later (1989-)",
    "timeless": "not tied to one era",
}

OPENINGS = {
    "A1": "quiz with two or three choices, answered within the story",
    "A2": "start with the opposite of common sense",
    "A3": "say the number first, reveal its meaning later",
    "A4": "time travel: take the listener to this spot N years ago",
    "A5": "poke at the oddness of a place or facility name",
    "A6": "address the listener's present situation (on a train, walking, at lunchtime)",
    "A7": "state the surprising result first, then tell how it came about",
    "I1": "curiosity gap: put an unknown right next to something the listener knows",
    "I2": "state the common assumption first, then break it",
    "J1": "cold open: start with the key line or quote",
}

STRUCTURES = {
    "B1": "mystery: question, one hint, answer",
    "B2": "before and after",
    "B3": "rule of three: two ordinary items, the third one breaks the pattern",
    "B4": "small story: person, trouble, idea, outcome",
    "B5": "the object or place tells its own story in the first person (use rarely)",
    "B6": "callback to a story already told today (only when trip memory has one)",
    "B8": "era relay: fast-forward the same spot through the ages",
    "B9": "compare with another place or something famous",
    "F1": "tension and release: build up seriously, release with a light punchline",
    "F4": "reversal: roles or cause and effect turn out the other way round",
    "G1": "mini hero's journey: hardship, challenge, achievement",
    "G2": "irony: a twist of fate, a name that means the opposite",
    "G3": "rivalry between two villages, towns or cities",
    "G4": "spotlight on nameless people",
    "G5": "the surprising true identity (\"it was actually...\")",
    "G6": "first, only or birthplace",
    "G7": "chain: A led to B, B led to C",
    "G8": "historical what-if, clearly framed as imagination",
    "G9": "zoom out or in: earth, the country, this road",
    "G10": "aftermath: end with what happened afterwards",
    "J4": "chain of whys",
    "J6": "counted hints (\"two hints\"), answered within the story",
}

STYLES = {
    "plain": "warm, conversational guide",
    "H1": "folktale (\"むかしむかし\")",
    "H2": "play-by-play commentary",
    "H3": "news flash",
    "H4": "imagined interview, clearly framed as imagination",
    "H5": "the listener is the main character (\"if you were a traveller in Edo...\")",
    "H6": "confidential whisper (\"ここだけの話ですが\")",
}

DEVICES = {
    "C1": "a line of dialogue from a person in the story",
    "C2": "sound, touch, smell, taste or weight (never sight)",
    "C3": "compare with something everyday",
    "C4": "the narrator lightly pokes fun at their own line",
    "C5": "one line of the narrator's own reaction",
    "C6": "a pause before the answer (write it with 、 or …)",
    "C7": "short line after a long one",
    "D1": "suggest one thing the listener can try next time",
    "D2": "\"what would you do?\"",
    "D3": "end on a line the listener can repeat to someone",
    "F2": "repetition for comic effect",
    "F3": "mitate: liken the place to an everyday object",
    "F5": "exaggerate, then take it back",
    "F6": "one-person boke and tsukkomi",
    "F7": "light wordplay (rarely)",
    "I3": "connect to the listener's daily life",
    "I4": "put the strongest line last",
    "I5": "concrete people, objects and feelings instead of abstract words",
    "I6": "invite a nod (\"〜ですよね\")",
    "I7": "turn a distance or duration into travel time",
    "J2": "parallel phrases",
    "J3": "a list of three",
    "J5": "close by echoing the title",
}

# Laughter and whispering are out of place in memorial, war and disaster stories.
LIGHT_ONLY = {"F1", "F2", "F5", "F6", "F7", "C4", "H6"}

# Hedges and source attributions belong on the screen and in the source list, not in the spoken story.
HEDGE_PATTERNS = ["諸説あり", "現存状況", "保証するもの", "保証しません", "資料によると", "確認できません", "確認されていません", "断定でき"]


def _catalogue(title, entries):
    return title + ":\n" + "\n".join(f"  {k}: {v}" for k, v in entries.items())


TECHNIQUE_GUIDE = "\n".join([
    _catalogue("Openings (pick one)", OPENINGS),
    _catalogue("Structures (pick one)", STRUCTURES),
    _catalogue("Narration styles (pick one; plain most of the time, the others now and then)", STYLES),
    _catalogue("Devices (use one or two)", DEVICES),
])

SPEECH_RULES = """How to write the spoken story (speech):
- 3-6 short sentences, about 20-30 seconds when read aloud, in a warm conversational voice (です・ます, 〜なんです, 〜だったそうです). The narrator is a curious local guide who enjoys a good story.
- Hook first, punchline last. Do not give the answer away in the first sentence.
- Make a person the main character when the facts allow: who was in trouble, what they did, how it turned out.
- One surprise per story. Leave the rest for other stories.
- Turn numbers into something the listener can feel (450 kg ≈ 6-7 grown men, 870 m ≈ a 10-minute walk). Such conversions and rough figures ("about 200 years ago") are allowed in the spoken story.
- You may add one or two sentences of widely known general knowledge needed to understand the story (e.g. what a 筆子塚 is). List them in general_knowledge. Never add local facts that are not in the materials or claims.
- No source names ("〜の資料によると") and no hedges ("諸説あります", "現存状況は確認できません") in the spoken story; the screen text and source list carry them. Legends and traditions must still sound like legends ("〜と伝わっています").
- End by bringing it back to here and now (this road, this station, the next time the listener passes).
- Never say or imply the listener can see something.
- Pick one opening, one structure and one narration style from the catalogue, and one or two devices, and report their codes. Vary them: do not use the same opening or structure as the stories listed in recent_techniques.
- tone is "serious" for memorial, war, disaster and death stories, otherwise "light". Serious stories never use F1, F2, F5, F6, F7, C4 or H6.
- punchline: the one line a listener would repeat to someone. If the facts have no such line, leave it empty: an empty punchline keeps the story out of automatic guidance, which is better than a dull one."""
