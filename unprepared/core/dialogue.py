"""Everything anybody says, with variety.

Two kinds of talk come out of here:

* **Lines** - situational remarks (greeting the player, a guard's warning, a merchant
  refusing stolen goods...). ``line(kind, rng, **fmt)`` picks one of several phrasings
  so the same situation is not worded the same way twice in a row.
* **Conversations** - short exchanges between two NPCs who meet: a greeting suited to
  the time of day, a reply, one or two topical exchanges coloured by who they are
  (a guard grumbles about the watch, the smith about iron, the innkeeper about
  thirsty customers) and a goodbye. ``build_conversation`` returns the scripted
  lines; the world plays them out a few seconds apart as speech bubbles.

Nothing here touches game state - it is all text and random choice - so it is
trivial to extend: add strings to the tables.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------------------- situational lines
LINES: Dict[str, Sequence[str]] = {
    # the player talks to someone
    "greet_guard": ("Keep your nose clean, traveller. Move along.", "Nothing to see here. On your way.",
                    "Mind yourself on my street.", "Quiet day. Let's keep it that way.", "You lost, friend? The inn's that way."),
    "greet_fence": ("Got stolen goods? I'll buy them, no questions asked.", "Anything warm in your pockets? I pay fair. Quietly.",
                    "Keep your voice down and show me what you've got.", "The guards don't come in here. Business?"),
    "greet_merchant": ("Welcome! Take a look at my wares.", "Good day to you. Browse as long as you like.",
                       "Ah, a customer. What can I get you?", "Everything's fresh in. Have a look."),
    "greet_smith": ("Blades, helms, tools and good iron. Nothing else - I'm a smith, not a pedlar.",
                    "Mind the sparks. Looking for steel?", "If it's iron you want, you've come to the right forge.",
                    "I'll take ore off your hands, or sell you something sharp."),
    "greet_innkeeper": ("Welcome to the Drowsy Dragon! Ale, stew, or a bed for the night?",
                        "Sit anywhere, love. Rooms are ten a night, fifty the week.",
                        "You look like you could use a hot meal. Or a bed.", "Ale's fresh and the beds are clean. What'll it be?"),
    "greet_tailor": ("Looking for something finer to wear?", "Cloth, thread and quiet shoes - come in.",
                     "Mind the pins. What can I fit you for?", "Soft soles for soft steps, if you take my meaning."),
    "greet_closed": ("The shop's closed right now. Come back during opening hours.", "Not open yet, friend. Later.",
                     "We're shut. Try again when the sign's out."),
    "greet_asleep": ("Zzz... (fast asleep)", "Zzz... mm... not the candlesticks... zzz",
                     "(a snore, then a mutter) ...five more minutes..."),
    "greet_townsfolk": ("Morning to you.", "Fine day for it.", "Don't I know you? No? Well, good day.",
                        "Mind the well, the step's loose.", "If you're after Barnaby, he's at the store.",
                        "Lovely evening. Off to the inn?", "Haven't seen you about before."),
    "greet_townsfolk_night": ("Late to be out, isn't it?", "Can't sleep either?", "Keep your torch lit, the watch are twitchy."),
    # warnings and trouble
    "trespass": ("Hey! You've no business in here. Out!", "What are you doing in here? Get out!",
                 "This is private. Leave, now.", "Out! Before I call the watch."),
    "torch_law": ("It's the law to carry a lit torch after dark. Light one, now!", "No torch after dark? Light one or I'll assume the worst.",
                  "Torch. Lit. Now. Town law."),
    "skulking": ("You there! What are you skulking about for?", "Stand up straight. What are you up to?",
                 "Creeping about, are we? I'm watching you.", "I see you sneaking. Don't."),
    "skulking_citizen": ("Hey! What are you skulking about for?", "What's all this creeping? Stand up!", "I see you there. Stop that."),
    "halt": ("Halt right there, criminal scum!", "Stop! In the name of the watch!", "That's it - you're coming with me!"),
    "cry_for_help": ("Guards! Help! A criminal is committing crimes!", "Help! Thief! Somebody fetch the watch!",
                     "Guards! Over here, quickly!"),
    "caught_red_handed": ("Caught you red-handed!", "Again?! Stop right there, thief!",
                          "That's enough! One more and you're coming with me!", "You're under arrest the moment I get my hands on you!"),
    "thief_guards": ("Thief! Guards!", "Stop, thief! Guards!", "Someone's robbing me! Guards!"),
    "stolen_goods": ("That {item} is stolen! Guards!", "I know that {item} - it's stolen! Guards!",
                     "Get that hot {item} away from me! Guards!"),
    "cant_afford": ("I can't afford that right now - I've only {gold}g in the till.", "Not at that price, not today. The till has {gold}g.",
                    "Come back when I've sold something - {gold}g is all I have."),
    "wrong_trade": ("I don't deal in that sort of thing.", "Take that elsewhere - I'm a {role}.",
                    "Not my trade. Try Barnaby."),
    "cry_response": ("A cry for help! On my way!", "Trouble! Hold on!", "I heard that - coming!"),
    "investigate": ("What was that? I'd better take a look.", "Hm? Who's there?", "Did you hear that? I'll check."),
    "gone": ("Gone... but I'll know that face when I see it.", "Slipped away. Not for long.", "Nothing here. Eyes open, then."),
    "woke_up": ("Who's there?! Making all that noise!", "What in blazes... who's there?", "Wha-? Who's making that racket?"),
    "cell_noise": ("Keep it down in there!", "Quiet, you!", "Rattle those bars all you like."),
    "leave_late": ("It's late. Time for you to go - I want to turn in.", "Off home with you, it's past my bedtime.",
                   "I'll be locking up now. Out you go, there's a good fellow."),
    "leave_again": ("I said it's late. Off with you, I'm not asking again.", "Still here? Out. I mean it.",
                    "Don't make me say it a third time."),
    "leave_now": ("Right, that's it. Out!", "Enough! Out of my house!", "That does it. Out!"),
    "locked_out": ("Locked. I'll wait out here.", "Not open yet? Give it a minute.", "Hm, shut. They'll be along.",
                   "Where is everyone? I'll wait."),
    "no_food": ("There's nothing to eat! Has someone been at the food?", "Empty! Who's had my supper?",
                "Not a crumb left. Thieves, I'll wager."),
    "shopping": ("I'll take two of those.", "How much for the honey?", "That's dearer than last week!", "Just looking, thank you.",
                 "Put it on my account, would you?", "Fresh in, you say? I'll have one."),
    "working_smith": ("*clang* *clang*", "Hotter. It needs to be hotter.", "There's a good edge coming on this one.",
                      "*the bellows wheeze*"),
    "working_kitchen": ("Pots on, Hilde!", "Stew's nearly ready.", "Mind the bread, it's catching!"),
    "working_porter": ("Where d'you want these, Barnaby?", "*grunts under a crate*", "That's the last of the wine."),
    "cleaning": ("Who left this here?", "Ale rings everywhere. Honestly.", "Mind your feet, I'm sweeping."),
    "drinking": ("Another, Hilde!", "Best ale in the county, this.", "*sips* Ahh.", "Same again, when you've a moment."),
    "rent_night": ("{Room} is yours for the night. Sleep well - checkout's at noon.",
                   "Ten gold and the night is yours. {Room}, up the hall."),
    "rent_week": ("A week in {room}, then. I'll see you're not disturbed.", "Fifty for the week - {room} is yours till then."),
    "rent_more": ("Staying on? {Room} is yours till noon in {nights} days, then.",
                  "Another night in {room}. I'll keep the bed made up."),
    "rent_none": ("I'm full up tonight, sorry. Try again tomorrow.",),
    "rent_over": ("Your rent's run out, love. Time to settle up or move along.", "Checkout was noon. Out you come."),
}

# ----------------------------------------------------------------------------- conversations
GREETINGS: Dict[str, Sequence[str]] = {
    "morning": ("Morning, {other}.", "Up early, {other}!", "Good morning to you, {other}.", "A fine morning, {other}."),
    "day": ("Afternoon, {other}.", "Well met, {other}.", "{other}! Good to see you.", "Busy day, {other}?"),
    "evening": ("Evening, {other}.", "There you are, {other}.", "Good evening, {other}.", "Long day, {other}?"),
    "night": ("Late for you, {other}.", "Can't sleep, {other}?", "Still up, {other}?"),
}
GREETING_REPLIES = ("And to you, {other}.", "Same to you.", "Aye, {other}. Yourself?", "Can't complain, {other}.",
                    "Well enough, thank you.", "Tolerable, tolerable.")

# (opener, reply) pairs; {other} is the listener's name. Role-specific topics are used when either speaker has the role.
TOPICS: Dict[str, Sequence[Tuple[str, str]]] = {
    "weather": (("Warm one today.", "Aye, the dust on the street says so."),
                ("Wind's turning - rain by morning, I'd say.", "My knees agree with you."),
                ("Lovely light on the street today.", "It is. Makes the place look almost respectable.")),
    "town": (("Have you seen the state of the well step?", "Someone will break an ankle on it."),
             ("Quiet lately, hasn't it been?", "Too quiet. Makes the watch nervous."),
             ("Did you hear about the candlesticks going missing?", "Barnaby's still fuming about it."),
             ("The inn was lively last night.", "Fenwick was, you mean.")),
    "trade": (("Prices at the store have crept up again.", "Everything has. Except my wages."),
              ("Mirelle has new cloth in from the south.", "Pretty, I'm sure. Not that I could afford it."),
              ("Gareth's hammer never stops.", "You can hear it from the far wall.")),
    "guard": (("Anything on the watch, {other}?", "Nothing but cats and drunks. The way I like it."),
              ("The captain's got us doubling the rounds.", "After the business at the store? Fair enough."),
              ("Keep your door locked tonight, {other}.", "I always do. Mostly.")),
    "smith": (("How's the iron coming, Gareth?", "Stubborn. Like its owner, Hilde says."),
              ("That forge could warm the whole street.", "It warms my bones, that's enough."),
              ("Any ore left in that seam?", "Enough for a few more swords, if the lad keeps digging.")),
    "innkeeper": (("Is the stew on, Hilde?", "Since dawn. Sit down before Fenwick has it all."),
                  ("Rooms full tonight?", "Two of three. There's always one for a friend."),
                  ("The ale's good this week.", "Don't tell Fenwick or he'll never leave.")),
    "shopkeeper": (("Got any honey in, Barnaby?", "Two jars, and the bees want a raise."),
                   ("You've let Dorran loose on the crates again.", "He's strong. Strong and careless."),
                   ("Stock counted this morning?", "Every bottle. Twice.")),
    "tailor": (("Is that a new cloak, Mirelle?", "Velvet. Don't touch it with those hands."),
               ("Could you take in a coat for me?", "Bring it by. And bring coin.")),
    "gossip": (("Tamsin says there was someone creeping about last night.", "Tamsin says a lot of things."),
               ("Pell's sweet on the tailor, you know.", "Pell's sweet on anyone who'll sell him a cloak on credit."),
               ("Raz keeps odd hours.", "Raz keeps odd everything. Best not to ask.")),
}
FAREWELLS = ("Well, I'd best get on.", "Mustn't keep you.", "Take care, {other}.", "See you at the inn.",
             "Good day to you, {other}.", "I'll let you get back to it.")
FAREWELL_REPLIES = ("Mind how you go.", "Aye, see you.", "Till later, {other}.", "Don't work too hard.", "Go well.")


def time_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def line(kind: str, rng: random.Random, **fmt) -> str:
    """One of the phrasings for ``kind``, formatted."""
    options = LINES[kind]
    return rng.choice(list(options)).format(**fmt)


@dataclass
class Conversation:
    """A scripted exchange between two NPCs, played out by the world a few seconds per line.
    Casual chats break off as soon as either party has something better to do; an
    *official* exchange (a guard taking a theft report) is seen through unless somebody is
    asleep or alarmed, and may run ``on_finish`` afterwards. Lines are ``logged`` only when
    they are part of the player's story (a report), never idle gossip."""
    a: object                         # NPC
    b: object                         # NPC
    lines: List[Tuple[object, str]]   # (speaker, text) in order
    index: int = 0
    next_line_at: float = 0.0
    finished: bool = False
    official: bool = False
    logged: bool = False
    on_finish: Optional[Callable[[], None]] = None
    participants: Tuple = field(init=False)

    def __post_init__(self):
        self.participants = (self.a, self.b)


# --- a guard taking a shopkeeper's theft report -------------------------------------------
REPORT_LINES: Dict[str, Sequence[str]] = {
    "ask_what": ("All right, {merchant}. What's been taken?", "What's missing, {merchant}?", "Calm down. What's gone?"),
    "tell_what": ("{missing} - gone from {area}.", "{missing}. Cleared off {area} while my back was turned.",
                  "Look for yourself: {missing}, taken from {area}."),
    "guard_saw": ("I saw someone skulking about here myself. I'll have a word with them.",
                  "There was someone hanging about {area} who had no business there. I'll find them."),
    "merchant_glad": ("Do. And get my goods back.", "Good. I want every piece of it back."),
    "ask_seen": ("Did you see anyone suspicious?", "Anyone hanging about who shouldn't have been?"),
    "merchant_saw": ("Yes - someone poking about where they'd no business. I'd know the face again.",
                     "There was one, creeping about {area}. I'd know them if I saw them."),
    "guard_lead": ("Then I'll find them. Leave it with me.", "Good. I'll have a word with them."),
    "merchant_saw_nothing": ("Not a soul. It must have been done in the night.", "No. Whoever it was, they were quiet about it."),
    "guard_no_lead": ("Keep it locked up. I'll keep an eye out.", "Then there's not much to go on. I'll keep my eyes open."),
}


def build_report_exchange(guard, merchant, missing: str, area: str, guard_saw: bool, merchant_saw: bool,
                          rng: random.Random) -> Conversation:
    """The guard who answered a theft report takes it from the shopkeeper face to face. The
    replies follow what each of them actually saw: a guard with a sighting of their own needs
    no description; otherwise he asks, and the merchant answers according to whether anyone was
    caught poking about the premises."""
    name = short_name(merchant)
    fmt = dict(merchant=name, missing=missing, area=area)
    pick = lambda kind: rng.choice(list(REPORT_LINES[kind])).format(**fmt)   # noqa: E731
    lines: List[Tuple[object, str]] = [(guard, pick("ask_what")), (merchant, pick("tell_what"))]
    if guard_saw:
        lines += [(guard, pick("guard_saw")), (merchant, pick("merchant_glad"))]
    else:
        lines.append((guard, pick("ask_seen")))
        if merchant_saw:
            lines += [(merchant, pick("merchant_saw")), (guard, pick("guard_lead"))]
        else:
            lines += [(merchant, pick("merchant_saw_nothing")), (guard, pick("guard_no_lead"))]
    return Conversation(guard, merchant, lines, official=True, logged=True)


def short_name(npc) -> str:
    """'Shopkeeper Barnaby' -> 'Barnaby', 'Guard Captain Vance' -> 'Captain', 'Raz the Fence' -> 'Raz'."""
    name = npc.name
    for prefix in ("Shopkeeper ", "Guard Captain ", "Guard ", "Jailer "):
        if name.startswith(prefix):
            rest = name[len(prefix):]
            return "Captain" if prefix == "Guard Captain " else rest
    return name.split(" the ")[0]


def build_conversation(a, b, hour: int, rng: random.Random, exchanges: Optional[int] = None,
                       recent: Optional[Sequence[str]] = None) -> Conversation:
    """Greeting, reply, one or two topical exchanges coloured by the speakers' roles, goodbye, reply.
    Exchanges whose opener is in ``recent`` are avoided so the same gossip does not do the rounds
    twice in an afternoon."""
    na, nb = short_name(a), short_name(b)
    recent = set(recent or ())
    lines: List[Tuple[object, str]] = []
    lines.append((a, rng.choice(list(GREETINGS[time_of_day(hour)])).format(other=nb)))
    lines.append((b, rng.choice(list(GREETING_REPLIES)).format(other=na)))
    pool = ["weather", "town", "gossip"]
    for npc in (a, b):
        role = getattr(npc, "role_tag", "") or ("guard" if npc.is_guard else "")
        if role in TOPICS:
            pool.append(role)
        if npc.is_guard:
            pool.append("guard")
    if any(getattr(n, "can_trade", False) for n in (a, b)):
        pool.append("trade")
    count = exchanges if exchanges is not None else rng.choice((1, 1, 2))
    rng.shuffle(pool)
    for topic in pool[:count]:
        options = [pair for pair in TOPICS[topic] if pair[0] not in recent] or list(TOPICS[topic])
        opener, reply = rng.choice(options)
        # the person the topic is *about* (a smith topic addressed to the smith) should be the replier
        speaker, listener = a, b
        role_of_b = getattr(b, "role_tag", "") or ("guard" if b.is_guard else "")
        role_of_a = getattr(a, "role_tag", "") or ("guard" if a.is_guard else "")
        if topic == role_of_a and topic != role_of_b:
            speaker, listener = b, a
        lines.append((speaker, opener.format(other=short_name(listener))))
        lines.append((listener, reply.format(other=short_name(speaker))))
    lines.append((a, rng.choice(list(FAREWELLS)).format(other=nb)))
    lines.append((b, rng.choice(list(FAREWELL_REPLIES)).format(other=na)))
    return Conversation(a, b, lines)


def player_greeting(npc, hour: int, rng: random.Random) -> str:
    """What an NPC says when the player talks to them."""
    if npc.is_asleep:
        return line("greet_asleep", rng)
    if npc.is_guard:
        return line("greet_guard", rng)
    if npc.is_fence:
        return line("greet_fence", rng)
    if npc.can_trade:
        if not npc.is_open_for_business:
            return line("greet_closed", rng)
        role = getattr(npc, "role_tag", "")
        kind = {"smith": "greet_smith", "innkeeper": "greet_innkeeper", "tailor": "greet_tailor"}.get(role, "greet_merchant")
        return line(kind, rng)
    if time_of_day(hour) == "night":
        return line("greet_townsfolk_night", rng)
    return line("greet_townsfolk", rng)
