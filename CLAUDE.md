# CLAUDE.md — BOMI Care Robot (S15P11E102)

Design of record and working agreement for the conversational AI runtime on the robot.

**Reading order for a new contributor:** §1 → §2 → §3 → §4 → §5, then whichever of §6–§17 your task
touches. §21 (comment standard) applies to every line of code you write here.

**Authority:** for the *database*, `docs/database/mvp-erd.md` wins — it is the implementation
contract and the backend enforces it. For the *conversation runtime* (when to speak, how to speak,
safety timing, graph structure), this file wins. Long-form Korean rationale for the runtime lives in
`docs/design/care-bot-design.md`.

---

## 1. What we are building

A **proactive care companion robot** for a senior living alone.

The robot listens continuously, **decides on its own when to speak**, remembers the senior across
sessions, handles medication and appointment reminders, answers everyday questions, greets the
senior at the door, and escalates safety concerns to a family guardian. All robot output is spoken
through TTS.

### Reframing — read this before proposing features

The original brief sounded like an "information chatbot with RAG." It is not. For someone living
alone, information delivery is the *least* important part. Three pillars carry the product:

| Pillar | Why it matters |
| --- | --- |
| **Safety** | Detecting the *absence* of activity and escalating. The real killer feature. |
| **Emotional support** | Loneliness is problem #1. The robot is a *companion* first. |
| **Cognitive support** | Orientation questions, repetition tolerance, early decline signals. |

Medication, weather, and clinic lookup sit **on top** of these three. Do not let retrieval features
crowd out the pillars.

### Concrete needs the three pillars imply

**Safety.** Non-response detection and escalation. Emergency triage that *routes*, never diagnoses.
Occupancy awareness from the door sensor. Late-night wandering.

**Emotional.** Ordinary check-ins ("have you eaten?"). **Reminiscence** — inviting old stories has
real therapeutic value and is the core emotional loop. Depression signals (falling word count,
rising negative expression). **Bereavement handling** — spouses and friends have died; surfacing a
dead spouse as if alive is one of the worst failures this system can produce.

**Cognitive.** Orientation ("what day is it?") is *by far* the most frequent question class, and
early dementia makes it repeat. Cognitive stimulation (light quizzes/games). Conversation-pattern
change as an early signal.

**Health beyond medication.** Seniors often do not feel hunger or thirst, so **skipped meals and
dehydration** frequently matter more than pill timing. Proactive "have a glass of water" nudges.

**Everyday information.** Weather as an **action**, not a number. Nearby clinics/pharmacies.
Korean welfare programs (노인맞춤돌봄서비스, 응급안전안심서비스, 기초연금) — good RAG corpus.

### Non-goals

- **Fall detection.** Out of scope: data and accuracy are both prohibitive at our timeline.
- **Medical decisions.** The robot never computes a dosage and never makes a medical judgement
  (this is also a hard rule in the ERD contract).
- **Therapy.** On self-harm signals the robot responds warmly and hands off to a human. It does not
  try to hold the conversation.

**Note:** vision *does* exist in this product, but only for `RESTING`/`AWAKE` transitions
(see §10). It is not a safety camera and it stores no frames, joints, track IDs, or face features.

---

## 2. Team context — write for the reader, not the compiler

Most of the team has **high ambitions but little hands-on experience with LangChain, RAG, or
conversational design**. Hardware and backend members will read this Python without being able to
read it quickly.

Therefore, in this repo:

- **Comments are a deliverable, not decoration.** §21 is mandatory, not aspirational, and
  **comments and docstrings are written in Korean** (identifiers and logs stay English).
- Never assume the reader knows what an embedding, a retriever, a graph node, or a checkpointer is.
  Explain inline or point at §3.
- Prefer boring explicit code. Three obvious lines beat one dense comprehension.
- When you use a library concept for the first time in a file, spend two comment lines on what it is
  and why we need it.

---

## 3. Glossary

| Term | Plain meaning here |
| --- | --- |
| **ASR / STT** | Speech → text. **External API.** Already implemented and tested. |
| **TTS** | Text → speech. **External API.** Already implemented and tested. |
| **VAD** | Voice Activity Detection. Cheap local "is someone talking right now?". Silero VAD. |
| **Wake word** | Local trigger phrase detector, so we are not streaming everything. openWakeWord. |
| **Embedding** | A list of numbers representing a text's *meaning*. Similar meaning → similar numbers. |
| **Vector search** | Finding stored texts whose meaning is closest to a query. Runs in Postgres via pgvector, **on the backend**. |
| **RAG** | Retrieval-Augmented Generation. Instead of hoping the LLM knows something, we retrieve relevant text first and paste it into the prompt. That is all it is. |
| **LangGraph node** | Just a Python function: takes the state dict, returns a dict merged into the state. |
| **LangGraph edge** | "After A, go to B." A **conditional edge** picks the next node at runtime. Returning the `END` sentinel stops the turn. |
| **State** | One dict flowing through one turn. See `ConvState`. |
| **Checkpointer** | LangGraph persistence keyed by `thread_id` (our senior id). Keeps `silence_level`, `last_spoke_at` etc. between runs. **Robot-local SQLite** (§5). |
| **SpeechProposal** | A *proposed* robot utterance awaiting permission. Never call this a "candidate" (§4). |
| **TTL** | Time-to-live: when a proposal expires and must be **discarded**, not deferred. |
| **Tier (T1–T4)** | How/whether something reaches the guardian (§9). |
| **Silence ladder** | Escalating probes when the senior has been quiet unexpectedly (§10). |
| **Barge-in** | The senior starts talking while the robot is still speaking (§13). |
| **Occupancy** | `HOME` / `AWAY` / `UNKNOWN`, derived from the entrance sensor (§11). |
| **Flyway** | Tool that applies versioned SQL migration files to Postgres. Schema changes are SQL files, not Hibernate magic (§19). |

---

## 4. Vocabulary — use the ERD's words

The database schema came first and the backend enforces it. **Use its vocabulary in code, comments,
and conversation.** Two vocabularies in one repo is how teams lose a week to confusion.

| Design concept (earlier drafts) | Use this instead | Where it lives |
| --- | --- | --- |
| user, elderly person | **senior** | `app_user.user_type = SENIOR` |
| family member | **guardian**, with `PRIMARY` / `SECONDARY` | `care_relationship` |
| profile | `app_user` + `care_record` | server DB |
| preferences / persona | `app_user.conversation_preferences` + `memory` | server DB |
| episodic memory | `memory` (long-term facts) + `conversation_summary` (compressed context) | server DB |
| raw conversation | `conversation` / `conversation_message` | server DB |
| medication, appointments, observations, alerts | `care_record` (by `record_type`) | server DB |
| unconfirmed extracted fact | **`fact_candidate`** | server DB |
| door greeting run | `scenario` (`scenario_type`, `external_event_id`) | server DB |

### Naming collision — non-negotiable

The ERD already owns the word **`candidate`** (`fact_candidate` = an unconfirmed fact awaiting
clarification/confirmation). Our gate's "proposed utterance" is a completely different thing.

> **Rule:** the gate's objects are **`SpeechProposal` / `proposal` / `proposals`**.
> The word `candidate` in this codebase always means `fact_candidate`.

---

## 5. System boundaries — who owns what

Three deployable units, three different machines, three lifecycles.

| Unit | Hardware | Owns |
| --- | --- | --- |
| **Robot runtime** (`robot/ai_chat/`) | Jetson Orin Nano 8GB | Python, LangGraph, audio, timing, gating, safety escalation decisions |
| **Entrance node** (`iot/raspberry-pi/`) | Raspberry Pi at the front door | In/out direction detection, heartbeat |
| **Backend + guardian app** | server | Spring Boot, PostgreSQL + pgvector, Flyway, the whole ERD, guardian API |

### Database ownership — this decision shapes everything

| Layer | Owner | Contents |
| --- | --- | --- |
| **Facts** | **Backend Postgres (the existing ERD, unchanged)** | `app_user`, `memory`, `care_record`, `fact_candidate`, `conversation*`, consent, coordination |
| **Operational state** | **Robot-local SQLite** | proposal queue, `silence_level`, `occupancy`, `last_spoke_at`, LangGraph checkpointer, cached TTS audio, outbound retry queue |

Why the split:

- **The checkpointer writes every turn.** Pointing it at the server would add a network round trip
  per turn and break entirely when offline. It is framework-internal state, not a business fact, so
  it does not belong in the ERD and is not Flyway-managed.
- The proposal queue and the silence ladder must survive a reboot but are meaningless to the
  guardian app. They are robot state.
- Conversely, facts must stay under backend authority: `fact_candidate`, consent gates, and PRIMARY
  coordination are correctness-critical and already implemented there.

### The API seam

`mvp-erd.md` §9 ("대화 문맥 조립") **is** the interface. Division of labour:

- **Backend = authority over facts and retrieval.** Vector search over `memory` and
  `conversation_summary`, the pre-filter (`senior_id`, `lifecycle_status = ACTIVE`,
  `verification_status != REJECTED`, visibility), reranking by similarity × `importance` × recency,
  top 3–10 only, plus consent gating and the `fact_candidate` lifecycle.
- **Robot = authority over timing and delivery.** Whether to speak at all, when, how long, how it
  sounds, barge-in, and the safety ladder.

A pleasant consequence: §8's "do not vectorize the profile" is enforced structurally, because the
backend already separates exact-lookup data from vector-searched data.

**Honest cost:** offline means no vector search, so long-term memory disappears. Mitigate with a
local read cache of the profile plus top-N memories, refreshed periodically. Accept that a degraded
offline robot has shallower memory; do not accept a mute one (§18).

### Transport

MQTT, per `docs/mqtt/topic-convention.md`. **Run the broker on the Jetson**, not in the cloud: the Pi
stays a thin publisher, and the entrance keeps working when the internet does not.

---

## 6. Runtime architecture

Three ingress paths converge into one response pipeline. **Judgment nodes sit above generation
nodes**: we decide *whether* and *how* before we decide *what*.

```
[senior utterance]      [scheduler]        [door sensor]
    ASR text         meds/meals/water      in/out event
        |                    |                   |
        v                    |                   v
 note_interaction            |            door_event  --> occupancy applied
   clock/ladder reset        |             (a fact: bypasses the gate)
   occupancy -> HOME         |                   |
   barge-in handling         +---------+---------+
   back-channel -> END                 v
        |                   +------------------------+
        |                   | proactive_gate         |--> silent --> END
        |                   | "may I speak now?"     |
        |                   +----------+-------------+
        v                              |
 +------------------+                  |
 | safety_triage    |                  |      +---------------------------+
 | emergency /      |------ T1 ---------------> escalation                 |
 | self-harm        |                  |      | outbox -> notify_guardian |
 +--------+---------+                  |      +---------------------------+
          v                            |
 +------------------+                  |
 | context_read     | <----------------+   backend: assembled context
 | (backend call)   |                      + local cache fallback
 +--------+---------+
          v
 +------------------+
 | classify_intent  |   (skipped when the proposal already knows)
 +--------+---------+
   +------+--------+----------+-----------+----------+--------------+
   v      v        v          v           v          v              v
 info companion schedule  emotional   greeting  onboarding   clarification
                            (T3)      (§11)      (§12)          (§12)
   +------+--------+----------+-----------+----------+--------------+
          v
 +------------------------------+
 | response_shaper              |  short / one thing / action-oriented / terse
 | splits into sentences        |
 +--------------+---------------+
                v
        emit (non-blocking TTS)
                v
               END
```

### Node responsibilities

| Node | Responsibility |
| --- | --- |
| `note_interaction` | First reactive node. Resets clocks and `silence_level`, forces `occupancy = HOME`, handles barge-in, ends the turn on a back-channel. |
| `door_event` | Applies occupancy immediately, fires move-to-door, creates a short-TTL greeting proposal, logs the raw event. |
| `proactive_gate` | Four gates, priority arbitration, or silence. |
| `safety_triage` | Emergency / self-harm classification. On T1 it skips the intent router entirely. |
| `escalation` | Writes to the outbound queue, then `notify_guardian`. Returns a calm utterance for the senior. |
| `context_read` | Calls the backend for assembled context; falls back to the local cache when offline. |
| `classify_intent` | Local, cheap, **no extra LLM round trip** (§16). |
| `handle_*` | Produce `response` text. They decide *what* to say, never *whether*. |
| `response_shaper` | Enforces §14 and splits into sentences. Every path goes through it. |
| `memory_write` | Records the turn, queues fact extraction, stamps `last_spoke_at`. |
| `emit` | Starts TTS asynchronously, returns a cancellable handle. |

---

## 7. The proactive gate — silence is a feature

**Nothing speaks on its own.** The scheduler, the silence ladder, the door sensor, and the
clarification flow all only *propose*:

```python
SpeechProposal = {
    "intent": "companion",              # which handler writes the sentence
    "priority": "low",                  # a key of PRIORITY_POLICY
    "seed": "Have you had lunch?",      # a hint, not the final sentence
    "expires_at": 1780000045.0,         # optional TTL, clock-based
}
```

The gate is a filter and referee, not a generator. Cascade, in order:

1. **Still valid?** Already handled, or TTL expired → **discard** (never retried).
2. **Quiet hours?** → defer, or pass with `terse=True` (see below).
3. **Cooldown elapsed?** → defer. Otherwise the robot becomes a nag.
4. **OK to interrupt?** VAD says someone is talking → wait.

Then priority arbitration picks **exactly one** survivor. If none survive, the graph goes straight
to `END`. In LangGraph terms, "not speaking" means **never reaching `emit`** — there is no empty
response to suppress later.

### Priority policy matrix

"Bypass" = treat that gate as passed. **This table is the brain of the gate.** Behaviour changes are
table edits, not changes to the loop.

| Priority | Example | Quiet hours | Cooldown | Interruption |
| --- | --- | --- | --- | --- |
| `critical` | liveness check after long silence | bypass | bypass | bypass |
| `high` | insulin, time-critical medication | bypass | bypass | respect |
| `event` | door greeting (§11) | respect → **terse** | bypass | respect |
| `clarification` | active `fact_candidate` re-ask (§12) | respect | bypass | respect |
| `medium` | ordinary medication, meals | respect | respect | respect |
| `low` | hydration nudge, gentle check-in | respect | respect | respect |
| `ambient` | small talk | respect | respect + longer | respect |

`event` is the only priority with a **third outcome**: during quiet hours it is neither blocked nor
passed normally — it passes with `terse=True` so a 2 a.m. homecoming still gets a short, quiet
greeting. Saying nothing would feel cold; full daytime length would be intrusive.

### Reasoning behind each gate

- **Validity** exists because proposals are not fire-and-forget. A 09:00 medication reminder is
  queued and at 08:55 the senior says "I took my pills" — the schedule handler marks it done and
  this proposal must vanish silently. Discard vs defer is the distinction that makes this gate
  useful.
- **Quiet hours** data is shared with the silence ladder. Quiet at 4 a.m. is not a warning sign, it
  is sleep. If you change the semantics here, check the ladder too.
- **Cooldown** prevents several timers landing together and producing a monologue.
- **Interruption** is the least reliable check and that is **accepted, not a bug to fix**. Audio
  alone cannot separate a television from a real conversation. Policy: when in doubt, hold back
  low-priority items and let critical ones through. Being over-cautious with small talk costs
  nothing.

---

## 8. Memory and the RAG boundary

**Do not put everything in the vector store.** This is the most common mistake in RAG projects and
it breaks correctness. Most memory is *pushed* into the prompt every turn; only two things are
*pulled* by similarity search. The existing ERD already reflects this — do not undo it.

### Push — exact lookup, never vectors

| Data | ERD home | Why not vectors |
| --- | --- | --- |
| Name, age, form of address, timezone, consent flags | `app_user` | "What are my meds?" needs an **exact** answer. Embeddings rank "blood-pressure pill" and "blood-sugar pill" as nearly identical and return the wrong one. |
| Medication, dose, schedule, appointments, allergies | `care_record` | Same, plus these are safety-critical. |
| Topics to avoid (e.g. a deceased spouse) | `app_user.conversation_preferences` / `memory` with deterministic filtering | Must be enforced **deterministically**. Probabilistic recall here is unacceptable. |
| Daily state: adherence, meals, water, sleep, mood, activity | `care_record` observations + daily metrics (§19) | Time-series queries, not similarity. |

### Pull — vectors, retrieved only when relevant

| Data | ERD home | Notes |
| --- | --- | --- |
| Long-term personal facts | `memory` (`content`, `keywords`, `embedding`, `importance`) | The raw material for natural conversation. Retrieval **must** combine similarity with recency and importance, or a knee complaint from six months ago outranks yesterday's. The ERD already specifies this. |
| Compressed conversation context | `conversation_summary` (`CONVERSATION`, `DAILY`) | Context compression, not fact storage. |
| Welfare programs, FAQs | reference document corpus (to build) | Long prose worth chunking. |

### Everyday information is not all RAG

- Nearby clinics/pharmacies → geo query / Places API
- Weather → API call
- Welfare programs, FAQs → vector RAG

### Write path — the safety rule

**Never write an extracted health or medication fact straight through.** If ASR mishears a mumbled
"I don't take the blood pressure pill in the morning any more" and we silently delete a schedule,
that is a dangerous bug.

The ERD already solves this, more thoroughly than our original design: extraction produces a
**`fact_candidate`**, and only `confirmed_value` is materialized. Respect the whole contract:

- One field re-asked at a time (`missing_fields` holds field names, not question text).
- Low STT confidence is a first-class reason (`LOW_RECOGNITION_CONFIDENCE`) — use it.
- Sensitive values get read back in full for explicit confirmation even when unambiguous.
- Silence, topic change, "글쎄", "아마도", unclear STT, or answering a *different* candidate do
  **not** count as confirmation.
- **One active candidate queried per conversation.** This is a dialogue-policy rule and the graph
  must enforce it (§12).

### Orientation repetition — a design principle, not a bug

Seniors ask "what day is it?" repeatedly; early dementia makes it frequent.

- **The 10th time must be answered as warmly as the 1st.** Never put "asked 9 times already" into
  the prompt — it will leak into tone.
- But **do log the repetition**: rising repetition is a cognitive-decline signal and belongs in the
  T2 trend report.

Splitting these two destinations is what makes both behaviours possible at once. This is the
clearest example of why the store split in this section matters.

---

## 9. Guardian escalation tiers

The senior and the guardian have **conflicting interests**. A robot that reports everything to your
children is a robot you stop confiding in — and then the emotional pillar dies. These tiers are the
product's ethics, not a notification setting.

| Tier | Contents | Consent | Delivery |
| --- | --- | --- | --- |
| **T1** | explicit danger ("my chest hurts"), explicit request ("call my son"), **prolonged non-response**, self-harm | not required | immediate |
| **T2** | adherence, meals/water/sleep, activity level, mild mood trend, outing frequency | not required (notification) | one daily batch |
| **T3** | accumulated depression signals, loneliness, bereavement, family conflict | **required** | deferred, after asking |
| **T4** | everyday grumbling, reminiscence, anything marked "just between us" | — | **never sent** |

Rules:

- **T3 timing matters more than T3 wording.** Listen in the moment; ask about sharing *later*, at a
  natural point. Interrupting a confession with "shall I report this?" is the worst possible move.
- **T4 must be real.** The senior has to believe it exists, or T3 never happens.
- **Self-harm overrides T3.** Even given "don't tell anyone", escalate as T1. Respond warmly, then
  hand off. Do not play counselor.
- **Prefer false positives on T1.** A missed emergency is far worse than a dismissible ping. Make
  the alert cheap to dismiss ("please check on them") rather than dialing emergency services, so we
  can afford a sensitive threshold.
- **Consent is two-layered:** one coarse setup ("health is fine to share, ask me about feelings")
  plus per-event confirmation for sensitive items. Asking every time erodes trust.

### Reconciling tiers with the ERD's consent model

These are four different mechanisms and they must not be confused:

| Mechanism | Question it answers |
| --- | --- |
| `app_user.*_consent_status` (personalization / health_data / schedule / guardian_sharing) | May we *store and use* this category of data at all? |
| `care_relationship.care_management_permission_status` + `ACTIVE` + `PRIMARY` | May this guardian *confirm or change* sensitive data on the senior's behalf? |
| `memory.visibility` | Who may see this individual memory row? |
| **T1–T4 (this section)** | Urgency and privacy routing for an *outbound guardian notification*. |

Consequences:

- T2 and T3 must check `guardian_sharing_consent_status` before sending.
- **T1 proceeds regardless of sharing consent**, because it is life-safety. This is a deliberate
  product decision: state it plainly in the consent copy so it is not a surprise.
- **T4 needs a `memory.visibility` value meaning "robot only, never shared."** Confirm this exists
  in the code dictionary; if not, it is a required addition (§19).
- `fact_candidate` confirmation and T3 consent are **not** the same thing. The former confirms *a
  fact before writing it*; the latter asks permission to *share a feeling*. Do not reuse one flow
  for the other.

---

## 10. Safety detection with weak signals

We have **three** signals: **voice**, the **door sensor**, and **rest state** (vision
`RESTING`/`AWAKE` transitions). Nothing else. They are complementary:

- The door sensor says whether the senior is **home**.
- Rest state says whether they are **resting or awake**.
- Voice says whether they are **all right**.

### The dangerous mistake

Treating "time since last utterance" as risk. Sleeping, going out, watching TV, and simply not
feeling chatty all look identical to a naive counter. False positives explode, the guardian starts
ignoring alerts, and **then we miss the real emergency**.

**Core idea: do not measure silence — actively test it.**

### The silence ladder

```
silence grows
   |
   v
Is this absence expected?  --- yes ---> wait (normal)
   occupancy == AWAY
   rest state == RESTING
   inside quiet hours
   matches the routine baseline
   |  no
   v
Probe 1 (low):      "Have you had lunch?"     --- response ---> reset
   |  no response
   v
Probe 2 (high):     "Are you all right?"      --- response, or
   |  no response                                 ambient sound ---> reassured
   v
Probe 3 (critical): last chance, bypasses every gate
   |  no response
   v
T1 escalation to the guardian
```

Interpretation table for silence at home:

| Occupancy | Rest state | Meaning | Ladder |
| --- | --- | --- | --- |
| `HOME` | `AWAKE` | **suspicious** — awake, present, not responding | run, and accelerate |
| `HOME` | `RESTING` | normal — sleeping or resting | hold |
| `AWAY` | any | normal | stop |
| `UNKNOWN` | any | ambiguous (sensor conflict, comms loss, boot) | run conservatively |

Notes:

- The **routine baseline is the primary false-positive filter**. Trigger on "quiet when they are
  never quiet," not on raw hours. Learn the rhythm from the event log.
- A probe is simultaneously a **companionship utterance and a liveness test**. "Have you had lunch?"
  does not feel like surveillance. Keep it that way.
- **Ambient sound is a weak signal only.** TV noise could mean an active person or an empty room. It
  nudges a confidence score; it never decides alone. Judge locally, never record or store audio.
- Escalation is a **confidence score** over several weak signals (deviation from baseline + failed
  probes + ambient sound + time of day + occupancy + rest state), not a single threshold. Keep every
  threshold in `policy.py` — they are tuning dials, set empirically (§20).
- Probes are real utterances: they create a `conversation` and `conversation_message` rows, so
  `last_spoke_at` and probe counts stay derivable, and an unanswered probe conversation ends
  `FAILED`.

### Reactive (explicit) signals

- **Negation and tense are critical.** "It does *not* hurt" and "it hurt *yesterday*" must not
  classify as "it hurts." ASR noise plus elderly speech makes keyword matching fragile. Do not
  escalate on a single keyword hit — insert one confirmation turn — but keep recall high on the
  danger side.
- Self-harm → T1 immediately (§9).
- The robot triages severity and routes. It never diagnoses and never computes a dose.

---

## 11. Door sensor and occupancy

A Raspberry Pi at the entrance distinguishes **entry vs exit** (already built). The robot moves to
the door and greets in both directions. Each run is recorded as a `scenario`
(`scenario_type`, `external_event_id`), per `docs/scenario/homecoming-welcome.md`.

### One event, two effects — keep them separate

| Effect | Through the gate? | Why |
| --- | --- | --- |
| Occupancy transition | **No — applied immediately** | It is a fact about the world, not an utterance. Not the gate's business. |
| Greeting proposal | **Yes** | It is an utterance; it takes the four gates like anything else. |

Any detected speech immediately promotes `UNKNOWN`/`AWAY` → `HOME`. **Speech beats the sensor.**

### Greeting specifics

- **Very short TTL** (tens of seconds). "Welcome home" ten minutes late is worse than silence — the
  robot announces to an empty hallway. This is the first real use of gate #1: expired greetings are
  **discarded, not rescheduled**.
- Priority `event`: bypass cooldown, quiet hours become `terse` (§7).
- **Decouple movement from speech.** Issue the move-to-door command immediately; fire the greeting on
  its own TTL. Voice carries across rooms, so a slow or failed navigation must not swallow the
  greeting. If the TTL expired before arrival, drop it.
- **Detection vs anticipation.** Detection (sensor event) is what we build. Anticipation (moving to
  the door because the routine baseline predicts a return) is optional, low priority, and costs a
  robot idling in the hallway when wrong.

### The sensor knows direction, not identity

| Situation | Misfire | Mitigation |
| --- | --- | --- |
| Visitor enters | `AWAY` + IN read as the senior returning | verify by speech, or delay confirming `HOME` |
| Visitor comes and goes while the senior is home | count confusion | prefer an occupancy **count** over a boolean if the sensor supports it |
| Door opened, nobody passes | spurious transition | only transition on a confirmed passage |
| Delivery | pointless greeting | ignore fast IN-OUT pairs |

**Principle:** never treat the sensor as absolute truth. Combine it with speech and ambient sound,
and on any contradiction fall back to `UNKNOWN` and behave conservatively.

### Two-machine realities

- **Heartbeat is required.** Events alone cannot distinguish "nobody moved" from "the Pi died" —
  a silent failure in a safety system. The Pi publishes a periodic heartbeat; when it stops, the
  robot degrades `occupancy` to `UNKNOWN`.
- **Timestamp authority is the Jetson.** A Pi without a battery-backed RTC can boot with a wrong
  clock, and a wrong door timestamp corrupts both the routine baseline and TTL arithmetic. Treat the
  Pi's timestamp as advisory and **normalize to `clock.now()` on arrival** — this also keeps
  compressed-clock demos coherent (§15).

### New safety signals only the door log can see

| Pattern | Tier | Rationale |
| --- | --- | --- |
| Left and not returned for a long time | T2 → T1 if sustained | Previously undetectable: nobody home means the ladder never runs. |
| Late-night / pre-dawn exit | T2, T1 if repeated | **Wandering** is a hallmark dementia symptom. It is *activity*, not silence, so the ladder is structurally blind to it. |
| Door left open | T2 | Safety, security, and a cognitive signal. |
| Sharp drop in outing frequency | T2 (trend) | Depression / health decline. Gives us a second activity metric besides utterance volume. |

These live in a **separate watch loop** (`door_watch_tick`), not the silence ladder.

### Privacy

Door logs are movement surveillance. Send the guardian **aggregates and anomalies**, not a running
"left 14:03, returned 15:20" feed. The surveillance-vs-trust tension from §9 applies here too.

### The doorway is the best moment for actionable information

On the way out, in priority order — weather as an action ("it's raining, take an umbrella"),
unconfirmed medication ("did you take your pills?"), today's appointments. On return — water, a
check-in, rest if they were out a long time.

**But obey §14: pick the single most important item.** Do not dump three things at the door.

---

## 12. Contract-driven dialogues (onboarding and clarification)

These two are **not** creative generation and must not take the ordinary RAG path. They fill defined
slots under a contract the backend enforces.

### `handle_onboarding`

Runs the question set in `docs/database/onboarding-question-set-v1.json` as natural conversation.
The app and the robot share the same question codes, required fields, consent gates, normalization
schema, and final mapping — only the surface differs (`APP` controls vs `robotPrompt`).

- One field at a time. `askOneFieldAtATime` is a hard rule.
- Consent questions gate later questions (`prerequisiteConsent`).
- Sensitive answers require explicit confirmation of the full value before materialization.
- A session can be resumed across channels; `started_channel` stays, `answered_channel` varies.

### `handle_clarification`

Drives an active `fact_candidate` that needs re-asking or confirmation.

- **Exactly one active candidate queried per conversation.** The ERD states this and the graph must
  enforce it — otherwise the robot asks about three pending facts at once and breaks the contract.
- `missing_fields` holds field names; convert them to one short spoken question.
- `clarification_reason` selects the phrasing: a missing field, an ambiguous value, low STT
  confidence, a conflict with existing data, or sensitive confirmation.
- Priority `clarification` (§7): above small talk, below safety, bypasses cooldown.

### Prompt discipline for both

Give the LLM **very little freedom**. The prompt states the single field being collected, the
allowed answer shape, and an instruction not to ask anything else. Everything the backend will
validate should be constrained here rather than repaired afterwards.

---

## 13. Barge-in policy

The senior starts talking while the robot is speaking. **Default: the robot yields.** Hearing loss
means they often do not realize the robot is mid-sentence, and senior speech is always the more
valuable signal.

Three ways a naive "stop on any sound" breaks:

1. **Echo.** Speaker and microphone share a body, so TTS output returns through the mic and the robot
   interrupts itself. Apply AEC, or at minimum raise the VAD threshold during playback and ignore the
   first ~300 ms. **Fix this before testing proactive speech at all** — otherwise every gate bug
   report is actually echo.
2. **Back-channels.** Elderly conversation is full of short "응", "어", "그래", "그래서?". Stopping
   on those means the robot never finishes a sentence. Rule: **under ~1 s and in the back-channel
   list → keep talking.** A back-channel turn ends at `END` immediately; do not run the whole
   pipeline to answer "응".
3. **Losing half a sentence.** "Take two blood pressure pills, and the insulin—" cut off is
   dangerous. Feed TTS **sentence by sentence**, track `spoken_prefix`, and on interruption
   **requeue the remainder at its original priority**. Gate #1 dedupes it on the way back in, so it
   resumes naturally after the senior's turn is handled.

`response_shaper` already enforces "short, one thing at a time," so **sentence boundaries are
already safe cut points** — TTS discipline buys barge-in recovery almost for free.

**Critical exception:** for liveness probes and T1 confirmations, the interruption *is the answer* —
they are alive. Do not resume the probe; **reset the silence ladder.** Barge-in is a liveness signal.

**Implementation consequence:** `emit` must not block until playback completes; it returns a
cancellable handle. Playback outlives the graph run, so `speaking` / `spoken_prefix` have two owners
(the playback thread and the checkpointed state). **This is the most sync-bug-prone spot in the
system.** Settle the boundary before building on it.

---

## 14. Speaking rules (TTS constraints)

Output is voice, so these are hard constraints, not style preferences. `response_shaper` enforces
them and every path goes through it.

- **Short. One thing per utterance.** If retrieval produces three paragraphs, nobody can follow by
  ear. Say one thing and hand the floor back with a question.
- **Action-oriented, not data-oriented.** "It's cold, wear thermals," not "it is 3 degrees."
- Short sentences, unhurried, repeat on request (hearing loss).
- Robust to noisy ASR: dialect, slurring, dropped particles. When unsure, ask rather than guess.
- Warm and consistent on repeated questions (§8).
- Honour `terse` when the gate sets it (§7).

---

## 15. Clock injection (mandatory)

**Never call `time.time()` or `datetime.now()` outside `clock.py`.**

Verifying the silence ladder or the daily summary in real time would take a day per test, which
makes development and demos impossible. With an injectable clock, `SimClock(speed=8640)` runs a day
in ten seconds.

Applies to everything that reads time: cooldown, quiet hours, routine baseline, recency decay, TTLs,
probe intervals, `last_spoke_at`, `last_user_interaction_at`, and **door event normalization** (§11).

APScheduler runs on real time, so **compressed-clock runs need a manual tick path** that bypasses
the scheduler. Design both paths together, from the start. Retrofitting this is much harder.

---

## 16. Prompting and LLM budget

LangGraph should be used heavily — but **using LangGraph heavily and calling the LLM often are
different things.** Adding nodes is free; adding LLM calls costs 500–1500 ms each, and voice
conversation has roughly a **two-second budget** for the whole round trip.

> **Rule: at most one generation LLM call per turn.**

- Triage, intent classification, and back-channel detection are **local** — rules or a tiny model.
  Doing them with the LLM turns one round trip into three and blows the budget.
- If LLM-based classification is genuinely needed, fold it into the generation call and return JSON.
- Stream where possible: begin TTS on the **first finished sentence** rather than the full response.
  The sentence splitting built for barge-in (§13) doubles as latency hiding.

### Use LangGraph for what it is good at

Conditional routing (gate, triage, intent), state plus checkpointer, the `END` path for silence, and
**`interrupt` / human-in-the-loop** — which maps precisely onto the T3 deferred-consent flow (§9):
pause after listening, resume later with the senior's answer. Prefer it over hand-rolling a queue.

### Prompt assembly is a pure function, not inline strings

Put templates in `prompts/` as files and expose `build_prompt(ctx, retrieved, intent) -> str` as a
**pure function**, testable without the graph. Naturalness is mostly decided here, so iteration must
be cheap. Prompts are code: they get comments explaining purpose, which stores feed them, and the
expected output shape.

Assembly order (each item maps to a §17 criterion):

1. **System**: persona, speaking rules (§14), prohibitions (no diagnosis, never mention internal
   machinery), form of address.
2. **Fixed facts**: name, age, conditions, medication.
3. **Preferences and the avoid-list** — the avoid-list as a **prohibition**, not information. Given
   as facts, the model will happily use them.
4. **Today's state**: adherence, mood, last interaction.
5. **Memory**: retrieved `memory` rows and relevant summaries, dated, framed as "what you remember."
6. **Documents**: only for the `info` intent.
7. **Recent conversation**: 6–12 raw messages, per the ERD's context recipe.
8. **Current input and why we are speaking**: reactive, or the proposal's seed and priority.
9. **Output constraints restated**: one or two sentences, will be read aloud. **Repeat them at the
   end** — constraints stated only at the top get buried in long context.

Also pass **the last few phrasings used for this reminder type** and instruct the model to vary —
one prompt line that buys §17.8 outright.

---

## 17. What "natural conversation" means operationally

"Natural" is not a vibe to tune at the end; it is this checklist. Treat each line as testable.

1. **Short turns.** One idea, then hand the floor back. Long correct answers are failures here.
2. **Continuity.** References yesterday's knee pain, the grandson's visit. Needs retrieval with
   recency weighting, not a bigger prompt.
3. **Never re-asks known facts.** Asking someone's name twice destroys the illusion instantly.
4. **Warm on repetition.** The 10th "what day is it?" gets the 1st answer's tone (§8).
5. **Respects the avoid-list.** Never surfaces a deceased spouse as if alive. Deterministic.
6. **Knows when not to speak.** Well-timed silence reads as more natural than any phrasing.
7. **Survives bad ASR.** Asks a clarifying question instead of confidently answering the wrong thing.
8. **Varies phrasing.** The same reminder three days running must not be word-for-word identical.
9. **Never narrates its machinery.** No "based on my records", no "as an AI", no mention of tiers,
   proposals, candidates, or retrieval.
10. **Reminiscence works.** Can invite and follow an old story. Therapeutic value, and the emotional
    pillar's core loop.

Bank a small set of transcripts and replay them against these ten points. That is our regression
test for naturalness.

---

## 18. Hardware, network, and degradation

### Platform: Jetson Orin Nano 8GB Dev Kit

| Fact | Consequence |
| --- | --- |
| 8 GB LPDDR5 shared CPU/GPU | Enough, not roomy. Keep resident processes few; tune any local DB conservatively. |
| **No onboard storage** — microSD, or NVMe via M.2 Key M | See the write-reduction rules below. |
| 40 TOPS GPU | **Largely idle**, because STT/TTS/LLM/embeddings are all external APIs. VAD and wake word run fine on CPU. |
| Battery powered | Abrupt power cuts are rare; **tick frequency now costs battery**. |
| 7–15 W, active cooling | Continuous operation is fine; measure battery runtime empirically. |

**SD card wear is accepted by the team, but a card dying on demo day is still a project incident.**
Without an SSD purchase, do all four:

- **Reduce writes.** Buffer the event log (adherence, mood, utterance volume, door events) in memory
  and flush periodically. Batch episodic embedding writes, which are already asynchronous.
- **Move OS logging to RAM.** tmpfs for logs, no persistent journald — this removes a surprising
  amount of constant unrelated writing.
- **Relax durability, with one exception.** Disable synchronous commit and lengthen checkpoints for
  operational state. Losing the last few seconds of episodic data is fine; **losing a queued
  guardian alert is not** — the outbound queue writes synchronously.
- **Daily dump.** Copy the local DB to a USB stick or the server once a day. The dev kit has four
  USB 3.2 ports. This turns "card death" from an incident into an inconvenience.

Also: `silence_tick` has no reason to run every second — 60 s is plenty, and door events arrive by
MQTT push rather than polling, so idle CPU stays near zero.

### aarch64 (for anyone who has not hit this before)

The Jetson's CPU is ARM 64-bit; your development PC is x86. **Compiled programs are not
interchangeable between them.** Two practical consequences:

- Python packages usually install from **wheels** (pre-compiled). If no ARM wheel exists, pip
  compiles from source: slow, and it fails outright without build dependencies.
- Native extensions may need `make && make install` instead of a package-manager one-liner.

So: **run `pip install` on the actual device during step 1 of §22**, as a smoke test. "It works on my
laptop" discovered late is expensive.

### Network is the real bottleneck, not compute

A turn costs three to four external round trips: STT → LLM → TTS, plus embeddings for memory writes.

- **Latency budget ~2 s.** Stream STT, start TTS on the first sentence, keep classification local
  (§16). Move embedding *writes* off the turn path — nothing about storing yesterday's memory needs
  to happen while the senior waits.
- **Offline is a safety problem, not an inconvenience.** With no network the robot cannot speak at
  all, and cannot notify the guardian — precisely when it matters most. Two mitigations are
  **required**:
  - **Cached audio for critical utterances.** Pre-render a handful of probe phrases ("어르신,
    괜찮으세요?") to local audio files. The silence ladder then works without network.
  - **Local outbound queue with retry.** Never fire-and-forget a guardian alert. Persist, retry, and
    mark late deliveries as delayed. See also §19 (Outbox).
  - Optional but valuable: a local read cache of the profile and top-N memories so conversation
    degrades in depth rather than dying.

### Degradation order under resource or network pressure

Define it up front so it is not improvised: **shrink memory retrieval top-k → disable document RAG →
stop `ambient` small talk → reduce probe richness.** The safety path (ladder, triage, outbound queue)
stays alive to the very end.

---

## 19. Database work items

The existing 12-table schema is sound. **Nothing is a deletion target.** Everything below is
additive or a small modification. `fact_candidate` in particular is a *better* safeguard than our
original design specified — adopt it as-is (§8).

### Modify

| Table | Change | Why |
| --- | --- | --- |
| `app_user` | **quiet hours / sleep window** (explicit in `conversation_preferences` or its own column) | Read by the gate on every proactive tick and by the silence ladder. |
| `app_user` | **home coordinates** | Nearby clinic/pharmacy lookup has no source otherwise. |
| `robot` | **`occupancy_status`** (HOME/AWAY/UNKNOWN) + observed-at | The single most valuable safety input (§11). |
| `robot` | **entrance-node heartbeat timestamp** | Without it, "nobody moved" and "the Pi died" are indistinguishable — a silent safety failure. |
| `conversation_message` | **`trigger_type`** (USER / SCHEDULE / SILENCE_PROBE / DOOR_EVENT / CLARIFICATION) and **`priority`** on ROBOT rows | Three needs: auditing why the robot spoke at 3 a.m.; separating robot from senior volume in T2 activity metrics; retrieving recent phrasings to satisfy §17.8. |
| `memory.visibility` | **confirm a value meaning "robot only, never shared"** | This is T4. Without it, T3 cannot work (§9). Check the code dictionary in the Excel definition. |
| `care_record` | **tier (T1/T2/T3) on notification-type records** | `recipient_guardian_id` already exists; the tier can live in `details` or as a column. |

### Add

| Item | Notes |
| --- | --- |
| **`occupancy_event`** | Raw door-event ledger. `scenario` records the *greeting run*; this records the *fact*. Feeds routine-baseline learning and outing-frequency trends. A few rows per day. |
| **Daily activity metrics** | Adherence, meals, water, sleep, mood, utterance volume, outing count. T2 reads these as a time series. No clear home in the current schema. Daily aggregates, not raw periodic measurements — consistent with the ERD's "don't store every observation" stance. |
| **Outbox** — *promote from TBD to required* | A T1 alert fired during a network drop simply vanishes today. Unacceptable in a safety device. Robot-local retry queue plus server-side outbox. |
| **T3 consent queue** | Deferred "may I share this with your son?" items have no home yet. Decide: a `care_record` notification with a pending-consent status, or a small dedicated table. |

### Decide now

- **Embedding model and dimension.** Currently TBD, but a `VECTOR` column needs its dimension in the
  DDL, so it blocks. Upstage is chosen for Korean quality; confirm the dimension against the
  pgvector index limit in the pinned version. If it exceeds the limit, we lose the index and fall
  back to a full scan (likely survivable at our scale — measure).
- **pgvector enablement.** `memory.embedding` and `conversation_summary.embedding` exist in the ERD
  but were excluded from `V1__init.sql` because the entities are unmapped. A migration with
  `CREATE EXTENSION vector;` plus the columns and index is an open work item.

### Flyway rules (schema changes)

- Schema is built by **SQL migration files**; Hibernate only validates (`ddl-auto: validate`).
- **Never edit an applied migration.** Flyway checksums it; add `V{n+1}__...` instead.
- Entity change and migration go in the **same PR**.
- Naming: `V{number}__{description}.sql`, two underscores.
- Verify against real PostgreSQL locally, not just H2 — H2 will not catch array, JSONB, or vector
  differences.

---

## 20. Repo layout

> **This section was reconciled with the actual tree in S15P11E102-200.** Earlier drafts described
> a greenfield `ai/src/carebot/`. The robot runtime already existed as `robot/ai_chat/` with the
> package name `bomi_ai_chat`, so the runtime was added **into that package** rather than beside it.
> Paths below are the real ones — use them verbatim in imports.

The robot runtime lives under `robot/`, never inside the web backend — it is a long-running
process, not a request/response service.

```
S15P11E102/
├── CLAUDE.md                       <- this file
├── HANDOFF.md                      <- one-off handover for the runtime work
├── docs/
│   ├── database/                   <- ERD, question set, Flyway guide (AUTHORITATIVE for schema)
│   ├── architecture/, scenario/, mqtt/, api/, hardware/
│   └── design/care-bot-design.md   <- long-form runtime rationale (Korean)
│
├── backend/                        <- Spring Boot, Flyway, the ERD, guardian API
├── frontend/
│
├── robot/                          <- UNIT 1: on the Jetson
│   ├── ai_vision/, ros2_ws/, maps/, launch/, config/
│   └── ai_chat/                    <- the conversation runtime (Python)
│       ├── pyproject.toml
│       ├── README.md               <- how to run; SimClock usage; aarch64 install notes
│       ├── tests/
│       └── src/bomi_ai_chat/
│           ├── clock.py            <- §15. the ONLY place time.time() may appear
│           ├── policy.py           <- every tuning dial: priority matrix, cooldowns, TTLs, top-k
│           ├── config.py           <- environment variables only (keys, hosts, devices)
│           ├── state.py            <- ConvState schema + SpeechProposal
│           ├── graph/
│           │   ├── build.py        <- StateGraph wiring ONLY, no business logic
│           │   ├── ingress.py      <- note_interaction, route_ingress, back-channel routing
│           │   ├── gate.py         <- proactive_gate (PRIORITY_POLICY lives in policy.py)
│           │   ├── triage.py       <- safety_triage, escalation
│           │   ├── context.py      <- context_read, classify_intent, route_intent
│           │   ├── handlers.py     <- info, companion, schedule, emotional,
│           │   │                      greeting, onboarding, clarification
│           │   └── output.py       <- response_shaper, emit
│           ├── jobs/ticks.py       <- silence_tick, door_watch_tick, daily_summary_job,
│           │                          outbox_flush
│           ├── audio_io/           <- laptop/robot adapters, sounddevice backend, beam control
│           ├── llm/                <- Gemini client, medical flow, embedding router (EXISTS)
│           ├── stt/, tts/, weather/, db/   <- external clients (EXIST — delegate, do not rewrite)
│           ├── pipeline.py         <- input loop driver: capture -> STT -> app.invoke
│           ├── http.py, main.py, __main__.py
│           │
│           │   ── not created yet; each arrives with its ticket ──
│           ├── localstore/         <- SQLite: proposals, ladder, occupancy, checkpointer, outbox (202)
│           ├── notify/             <- guardian adapter, swap the channel here (202 iface -> 211)
│           ├── backend_client/     <- context assembly, fact_candidate, care_record, consent (204)
│           ├── prompts/            <- templates as files, versioned, never inline strings (204)
│           └── door/               <- entrance-node client, occupancy rules, heartbeat watch (208)
│
└── iot/                            <- UNIT 2: Raspberry Pi + sensor nodes, MQTT
    ├── raspberry-pi/, sensor-nodes/, jetson/, mqtt/
```

Rules:

- `graph/build.py` is wiring and nothing else. Business logic there gets moved.
- `backend_client/` is the **only** module that talks to the server; `localstore/` is the **only**
  module that touches local SQLite. Handlers never do I/O directly.
- **Every tunable number lives in `policy.py`**, with a comment on what raising or lowering it does.
  `config.py` is environment variables only. The two have different lifetimes and are **not**
  merged: `config.py` changes when you move deployments, `policy.py` changes when a product
  judgement changes. (Earlier drafts of this section said `config.py` — `policy.py` is correct.)
- `llm/`, `stt/`, `tts/`, `weather/`, `db/`, and `audio_io/` already exist and are tested.
  Handlers **delegate** to them; do not reimplement. `llm/router.py` already does embedding-based
  intent routing — filter with rules first and only delegate when genuinely ambiguous (§16).
- `db/` is medical *reference* lookup (hospital, pharmacy, drug). The senior's own facts and
  memories go through `backend_client/`. Never read memory through `db/ssh_tunnel`.
- The guardian channel is one adapter in `notify/`. Its shape must not leak into the graph.
- The Pi and the robot share payload schemas; on comms loss degrade `occupancy` to `UNKNOWN` —
  never trust the last event forever.

---

## 21. Commenting and documentation standard (mandatory)

**Comments and docstrings are written in Korean.** Identifiers, types and log messages stay in
English; the prose that explains *why* is Korean, because the audience is a Korean teammate who does
not read Python quickly and has never used LangChain. Section labels inside docstrings are Korean so
they can be skimmed.

### Module header

```python
"""능동 발화 게이트 — 지금 로봇이 말해도 '되는지'를 결정한다.

어디에 위치하는가
    스케줄러, 침묵 사다리, 현관 센서, 재질의 흐름이 모두 발화를 제안한다.
    아무도 직접 말하지 않는다. 이 모듈이 심판이 되어 정확히 하나만 통과시키거나
    침묵을 선택한다. 이 아래의 모든 것은 이미 허락이 떨어졌다고 가정한다.

왜 존재하는가
    타이머가 울릴 때마다 말하는 로봇은 잔소리꾼이 된다. 새벽 3시에 떠들고, TV 를
    끊고, 5분 전에 한 알림을 또 한다. '말하지 않기로 결정하는 것도 기능이다.'

읽는 값   last_spoke_at, audio_ctx, occupancy, proposals, quiet_hours
쓰는 값   gate_decision, terse, intent, user_input

참고
    CLAUDE.md §7 (우선순위 행렬)
"""
```

### Function docstring

```python
def proactive_gate(state: ConvState) -> dict:
    """제안된 발화들을 걸러서 최대 '하나'만 고른다.

    무엇을 하는가
        대기 중인 모든 제안을 네 게이트에 순서대로 통과시킨다. 살아남은 것들은
        우선순위로 경쟁하고 최고 하나가 이긴다. 아무도 살아남지 못하면 침묵한다.

    왜 이 순서인가
        가장 값싸고 결정적인 것이 먼저다. 이미 만료된 인사가 VAD 조회 비용을
        쓸 이유가 없다.

    누가 호출하는가
        build.py. 진입 라우터에서 trigger_type "proactive" 와 "door_event" 로 온다.

    무엇을 호출하는가
        is_still_valid, is_quiet_hours, is_in_cooldown, is_busy — 모두 값싸다.

    인자
        state: 여기서는 proposals, 런타임 타임스탬프, audio_ctx 만 의미가 있다.

    반환값
        {"gate_decision": "silent"}  -> build.py 가 END 로 보낸다. 이것이 성공이다.
        {"gate_decision": "speak", ...} -> context_read 와 핸들러로 진행한다.

    주의사항
        - 폐기(discard)와 연기(defer)는 다른 결과다. 인사는 만료되면 버려야 하고,
          복약 알림은 나중에 다시 와야 한다.
        - 우선순위는 게이트를 건너뛸 수 있다. 이 함수가 아니라 PRIORITY_POLICY 를
          고친다.
    """
```

Required sections: `무엇을 하는가`, `누가 호출하는가`, `무엇을 호출하는가`, `반환값`, and
`주의사항` wherever a subtlety exists. Add `왜 존재하는가` whenever the reason is not obvious from
the name.

### Inline comments explain *why*, never *what*

```python
# 나쁨 — 코드를 그대로 반복한다
if clock.now() > p["expires_at"]:   # 지금이 expires_at 을 지났으면

# 좋음 — 판단의 근거를 설명한다
# 인사의 TTL 은 약 45초다. 문이 열린 지 10분 뒤의 "어서오세요"는 침묵보다 나쁘다.
# 그래서 만료된 인사는 재스케줄이 아니라 폐기한다.
if clock.now() > p["expires_at"]:
```

### Also required

- **Introduce library concepts on first use.** Two Korean lines on what a retriever is, why we call
  it before the LLM, and what happens when it returns nothing.
- **Name the failure mode.** When code exists to prevent something, say what ("이게 없으면 ASR
  오인식이 복약 스케줄을 조용히 지운다").
- **Cross-reference this file.** `# CLAUDE.md §9 참고` beats re-explaining the tier system.
- **Constants carry their rationale and adjustment direction:**
  ```python
  # 1초 미만이면 어르신의 발화는 거의 항상 맞장구("응", "그래")다.
  #   올리면 -> 로봇이 문장 중간에 자꾸 멈춘다.
  #   내리면 -> 진짜 끼어들기를 무시한다.
  BACKCHANNEL_MAX_SEC = 1.0
  ```
- **Prompts are code.** Purpose, which stores feed them, expected output shape.
- Keep comments truthful. A stale comment is worse than none — update it in the same commit.

---

## 22. Build order

Each step exists because the next is untestable otherwise. Do not reorder without a reason.

0. **Clock injection (§15) + the `notify_guardian`/outbox interface (§18).** Both are painful to
   retrofit and both unlock testing for everything after. Also: run `pip install` **on the Jetson**
   now, not later (§18).
1. **`localstore` + `backend_client` for real.** Local SQLite (proposals, ladder, checkpointer,
   outbox) and the context-assembly call. Everything reads through these two.
2. **One reactive path end to end** — `handle_info` / `handle_companion`, a full senior-utterance
   round trip with the existing STT and TTS wired in. Measure the latency budget here (§16).
3. **Echo suppression (§13.1).** Before any proactive work. Skipping it contaminates every
   subsequent test.
4. **Proactivity** — `proactive_gate` + `silence_tick`, verified under the compressed clock.
5. **Door sensor integration (§11)** — MQTT, heartbeat, occupancy, greeting proposals with TTL. Needs
   the gate first. Robot navigation can come later; the greeting must not depend on it.
6. **Contract-driven dialogues (§12)** — onboarding, then clarification. These unblock the
   `fact_candidate` flow that the whole memory write path depends on.
7. **Triage and escalation last.** Signal tuning takes longest, and by now occupancy and rest state
   have removed most of the false positives you would otherwise be tuning against.

The classic failure mode is building proactivity and safety while the basic reactive loop is still
broken. Resist it.

---

## 22a. Progress reporting (mandatory)

Much of this build is delegated, and the person accountable for it must be able to judge the state
**without reading the code**. Four documents in `docs/carebot/` exist for that, and keeping them
truthful is part of finishing a ticket — not paperwork afterwards.

| Document | Answers |
| --- | --- |
| [`PROGRESS.md`](docs/carebot/PROGRESS.md) | What failed, what is unverified, what deviated from the plan, what is going well |
| [`VERIFICATION.md`](docs/carebot/VERIFICATION.md) | What to run, and what counts as success or failure |
| [`READING-ORDER.md`](docs/carebot/READING-ORDER.md) | Which files to read, in what order, and what to look for |
| [`CONCEPTS.md`](docs/carebot/CONCEPTS.md) | Vocabulary, and why each design decision was made |

**When to update `PROGRESS.md`:**

- **Every ticket push** — move the row, fill in the completion-condition results.
- **Whenever a decision changes** — record it in §3 (deviations) with the reason, even if it looks
  minor. Especially if it looks minor.
- **Whenever a new risk appears** — §2 is ordered by importance; put it where it belongs.
- **Whenever something that was failing starts passing** — removing a stale warning matters as much
  as adding a real one.

**When to update the other three:** `VERIFICATION.md` when a new way to check something exists, or
when success criteria change. `READING-ORDER.md` and `CONCEPTS.md` when a new module lands or a
design judgement is made that a reader would otherwise have to reverse-engineer.

**The rule that makes these documents worth reading:** never describe something as done when it is
only implemented. "Logic verified, hardware unverified" is the honest shape of most of this work,
and writing it that way is what lets someone else trust the parts that *are* finished.

---

## 23. Anti-patterns — reject these in review

- Calling `time.time()` / `datetime.now()` outside `clock.py`.
- Using the word `candidate` for a proposed utterance (§4).
- Putting profile, preferences, medication, or schedule data into vector search.
- Writing an extracted health or medication fact without going through `fact_candidate`.
- Querying more than one active `fact_candidate` in a single conversation.
- A handler deciding *whether* to speak, or doing I/O directly.
- Emitting text that has not passed through `response_shaper`.
- More than one generation LLM call in a turn; classification via an extra LLM round trip.
- Prompt strings inline in node functions instead of `prompts/`.
- Sending T2/T3 without checking `guardian_sharing_consent_status`; sending T3 without consent
  (self-harm excepted).
- Fire-and-forget guardian notifications with no outbox.
- Sending raw movement logs to the guardian instead of aggregates.
- Thresholds hard-coded in function bodies instead of `policy.py` (§20).
- Blocking on TTS playback inside `emit`.
- Trusting the door sensor over contradicting speech; trusting the last door event forever with no
  heartbeat check.
- Pointing the LangGraph checkpointer at the server database.
- Storing vision frames, joints, track IDs, or face features. Storing every periodic environment
  measurement.
- Letting the robot play therapist on self-harm signals, compute a dose, or make a medical
  judgement.
- Adding fall detection.

---

## 24. Open decisions — ask, do not invent

| Open item | Notes |
| --- | --- |
| `memory.visibility` has a "never share" (T4) value? | Check the Excel code dictionary. If absent it must be added (§19). |
| T3 consent queue location | `care_record` with a pending status, or a dedicated table (§19). |
| Embedding model dimension vs pgvector index limit | Blocks the vector migration (§19). |
| Daily activity metrics: `care_record` type or dedicated table | Affects the T2 summary query (§19). |
| Occupancy: boolean vs person count | Depends on sensor accuracy; drives visitor handling (§11). |
| MQTT topic and payload for door events, heartbeat interval | Align with `docs/mqtt/topic-convention.md` (§11). |
| Guardian channel implementation | Web app / push / SMS. Interface fixed, implementation open. |
| Robot navigation to the door | Deferrable; the greeting must not depend on it (§11). |
| Anticipatory move on predicted return | Optional. Detection-based greeting first (§11). |
| AEC vs threshold-only echo handling | Decide after measuring on real hardware (§13). |
| Far-field microphone quality | May be the real bottleneck; software cannot fix it. |
| Silence-ladder thresholds, back-channel list, retrieval top-k | Tuning dials, set empirically. |
| Battery runtime under continuous operation | Measure; it constrains tick frequency (§18). |
| Cognitive-stimulation content (quizzes, games) | Not designed yet. |
| Reference document corpus for welfare-program RAG | Source and chunking not decided (§8). |
