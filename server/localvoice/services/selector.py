"""Selection interface shared by the rule path and the LLM path (realtime-llm-design §4)."""
from dataclasses import dataclass, field


@dataclass
class SelectionInput:
    candidates: list            # ranked Candidate list (top N)
    language: str
    detail_mode: str
    transport_class: str
    course_confident: bool
    recent_titles: list         # titles of today's guides, oldest first
    memory_summary: str | None
    interests: dict
    boosts: dict
    local_time: str
    trigger: str = "context"
    intents: list = field(default_factory=list)  # active P1 overrides as labels
    # storytelling of the last stories told, newest last: {story_type, tone, length, techniques}
    recent_stories: list = field(default_factory=list)
    # languages the story is spoken in, one after another (language above is the screen's)
    narration_languages: list = field(default_factory=list)

    def __post_init__(self):
        if not self.narration_languages:
            self.narration_languages = [self.language]


@dataclass
class Selection:
    action: str                 # speak | stay_silent
    knowledge_id: str | None = None
    title: str | None = None
    text: str | None = None
    # per narration language: one spoken sentence fitted to the moment, played before the story's shared audio
    intros: dict = field(default_factory=dict)
    reason: str | None = None
    used_claim_ids: list = field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    error: str | None = None    # set when the LLM path failed → caller falls back to rules
