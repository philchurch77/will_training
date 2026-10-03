"""The deck: every challenge card, as the seeder writes it.

This is the coaching brief, the way seed_drills.py was for the old plan. The
research behind it (docs/chart/deck.md) comes down to a few rules, and
test_deck.py asserts them against every card:

* Every card has a score, so there is something to beat. Free play is the
  one exception, and it is there because play is training too.
* Weak foot first. A per-foot card asks for the weak foot's score before the
  strong one's, and a medal goes on the weaker of the two.
* One cue, about the result rather than the body: "make the cone believe
  you", not "lock your ankle".
* Alone, in the garden, with a ball, a rebounder, a goal and a few cones.
  No wall: the rebounder does that job.
* Two or three short sentences, second person, written for Will to read.

A move is described the same way here as in the drill library: there is one
chop, cut back with the inside of the foot in front of you, so the "inside
hook" from the research is the chop turn and not a second word for it. A
scissor pushes away with the same foot that circled; a step over pushes away
with the other. The Cruyff spins him away behind the standing leg.

Cards key off their slug and update in place. A card is never deleted: move
it to RETIRED and the seeder switches it off, leaving every play he made
against it alone.
"""

from .models import Card

# Eight moves, three levels each. The research picks four to six moves per
# four-week block and takes them to game speed; these are its two blocks.
# (slug, name, the name mid-sentence with its article, how to do it, cue for level 1, cue for
#  level 3)
MOVES = [
    (
        "chop",
        "Chop turn",
        "a chop turn",
        "Cut the ball back with the inside of your foot, in front of you, "
        "and go the way you came.",
        "Stop it dead, then gone",
        "Leave the cone going the wrong way",
    ),
    (
        "drag-back",
        "Drag back",
        "a drag back",
        "Put your sole on top of the ball, drag it back towards you, and "
        "take it away the way you came.",
        "Sole on top, then away",
        "Pull it away just before the cone",
    ),
    (
        "scissors",
        "Scissors",
        "a scissor",
        "Circle your foot around the front of the ball from the inside to the "
        "outside without touching it. Then push the ball away with the outside "
        "of that same foot.",
        "Make the ball believe you",
        "Make the cone believe you",
    ),
    (
        "matthews",
        "Matthews",
        "a Matthews",
        "Nudge the ball a little way with the inside of your foot, like you "
        "are going that way. Then push it the other way with the outside of "
        "the same foot.",
        "Small nudge, big push",
        "Push him onto the wrong foot",
    ),
    (
        "outside-hook",
        "Outside hook",
        "an outside hook",
        "Hook the ball round with the outside of your foot and turn your body "
        "with it, so you end up going back the way you came.",
        "Turn with the ball",
        "Turn before the cone gets you",
    ),
    (
        "cruyff",
        "Cruyff turn",
        "a Cruyff turn",
        "Shape like you are about to pass. Instead, drag the ball behind your "
        "standing leg with the inside of your foot and spin away.",
        "Sell the pass",
        "Fake it properly, then gone",
    ),
    (
        "elastico",
        "Elastico",
        "an elastico",
        "Push the ball out with the outside of your foot, then snap it back "
        "inside with the same foot in one motion.",
        "Out and back, one snap",
        "Snap it past the cone",
    ),
    (
        "body-feint",
        "Body feint",
        "a body feint",
        "Drop your shoulder and lean like you are going one way, without "
        "touching the ball. Then push it away the other way with the outside "
        "of your other foot.",
        "Lie with your shoulders",
        "Make the cone lean the wrong way",
    ),
]


def _move_cards():
    """Three cards for every move: on the spot, through the cones, past one."""
    cards = []
    for index, (move, name, inline, how, cue_one, cue_three) in enumerate(MOVES):
        order = 300 + index * 10
        cards += [
            {
                "slug": f"{move}-1",
                "name": f"{name}: on the spot",
                "pack": Card.MOVES,
                "instructions": (
                    f"{how} As many clean ones as you can in 30 seconds, weak "
                    "foot first."
                ),
                "cue": cue_one,
                "score_label": "clean ones",
                "per_foot": True,
                "timer_seconds": 30,
                "medals": (8, 11, 14),
                "move": move, "level": 1, "order": order,
            },
            {
                "slug": f"{move}-2",
                "name": f"{name}: cone run",
                "pack": Card.MOVES,
                "instructions": (
                    "Put five cones in a line, three big steps apart. Dribble "
                    f"down the line doing {inline} at every cone, then "
                    "come back. Use the clock to time it."
                ),
                "cue": "Quick, but every one clean",
                "scoring": Card.TIME,
                "score_label": "seconds, there and back",
                "medals": (300, 240, 190),
                "move": move, "level": 2, "order": order + 1,
                "needs_cones": True,
            },
            {
                "slug": f"{move}-3",
                "name": f"{name}: beat the cone",
                "pack": Card.MOVES,
                "instructions": (
                    "Put a cone ten big steps away. That is your defender. Run "
                    f"at it full pace, beat it with {inline} and sprint "
                    "past. Eight goes, swap feet every go, and count the clean "
                    "ones."
                ),
                "cue": cue_three,
                "score_label": "clean beats",
                "out_of": 8,
                "medals": (5, 6, 7),
                "move": move, "level": 3, "order": order + 2,
                "needs_cones": True,
            },
        ]
    return cards


CARDS = [
    # --- Quick feet --------------------------------------------------------
    # The research's foundation touches, as races against the clock. As a
    # five-minute warm-up they were autopilot and were retired; as a score in
    # 30 seconds they are a test of how fast his feet are.
    {
        "slug": "toe-taps-30",
        "name": "Toe tap race",
        "pack": Card.QUICK_FEET,
        "instructions": (
            "Tap the top of the ball with the bottom of your toes, swapping "
            "feet every time. Count every tap in 30 seconds."
        ),
        "cue": "Eyes off the ball by the end",
        "score_label": "taps",
        "timer_seconds": 30,
        "medals": (50, 60, 70),
        "order": 100,
    },
    {
        "slug": "foundations-30",
        "name": "Foundations race",
        "pack": Card.QUICK_FEET,
        "instructions": (
            "Tap the ball from the inside of one foot to the inside of the "
            "other. Count every touch in 30 seconds, and the ball has to stay "
            "between your feet."
        ),
        "cue": "Ball never leaves the box",
        "score_label": "touches",
        "timer_seconds": 30,
        "medals": (40, 50, 60),
        "order": 101,
    },
    {
        "slug": "inside-outside-30",
        "name": "One-foot inside, outside",
        "pack": Card.QUICK_FEET,
        "instructions": (
            "Use one foot only. Tap the ball with the outside of it, then the "
            "inside, and keep it going. Count the touches in 30 seconds, weak "
            "foot first."
        ),
        "cue": "Ball stays under you",
        "score_label": "touches",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (20, 28, 35),
        "order": 102,
    },
    {
        "slug": "pull-push-30",
        "name": "Pull, push race",
        "pack": Card.QUICK_FEET,
        "instructions": (
            "Pull the ball back with your sole, then push it forward with your "
            "laces, and keep it going. Count how many in 30 seconds, weak foot "
            "first."
        ),
        "cue": "Ball stays in reach",
        "score_label": "pull-pushes",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (15, 20, 25),
        "order": 103,
    },
    # --- Combos ------------------------------------------------------------
    # The warm-up combinations from the drill library, scored. The wording of
    # each move matches the library's.
    {
        "slug": "combo-step-over-cruyff",
        "name": "Step over into a Cruyff",
        "pack": Card.COMBOS,
        "instructions": (
            "Step one foot over the ball without touching it, then drag the "
            "ball behind your standing leg with the inside of that same foot "
            "and spin away. Count the clean ones in 30 seconds."
        ),
        "cue": "Sell the step over, then spin",
        "score_label": "clean combos",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (5, 7, 9),
        "order": 200,
    },
    {
        "slug": "combo-rollover-chop",
        "name": "Rollover into a chop",
        "pack": Card.COMBOS,
        "instructions": (
            "Roll the ball across your body with your sole, then chop it back "
            "the other way with the inside of your other foot. Count the clean "
            "ones in 30 seconds."
        ),
        "cue": "No pause in the middle",
        "score_label": "clean combos",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (8, 11, 14),
        "order": 201,
    },
    {
        "slug": "combo-double-scissor",
        "name": "Double scissor and go",
        "pack": Card.COMBOS,
        "instructions": (
            "Circle one foot round the front of the ball, then the other, "
            "without touching it. Push the ball away with the outside of "
            "whichever foot is nearer. Count the clean ones in 30 seconds."
        ),
        "cue": "Two circles, then gone",
        "score_label": "clean combos",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (5, 7, 9),
        "order": 202,
    },
    {
        "slug": "combo-l-turn",
        "name": "Drag back into an L-turn",
        "pack": Card.COMBOS,
        "instructions": (
            "Roll the ball back with your sole, then cut it behind your "
            "standing leg with the inside of that same foot. Come out facing "
            "square, not all the way round. Count the clean ones in 30 seconds."
        ),
        "cue": "Draw an L on the grass",
        "score_label": "clean combos",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (6, 8, 10),
        "order": 203,
    },
    {
        "slug": "combo-croqueta-chop",
        "name": "Croqueta and chop",
        "pack": Card.COMBOS,
        "instructions": (
            "Jab the ball sharply from the inside of one foot to the inside of "
            "the other. Then chop it back the way it came with the inside of "
            "that foot. Count the clean ones in 30 seconds."
        ),
        "cue": "Sharp jab, then cut it back",
        "score_label": "clean combos",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (7, 10, 13),
        "order": 204,
    },
    {
        "slug": "combo-tap-drag-turn",
        "name": "Tap, tap, drag, turn",
        "pack": Card.COMBOS,
        "instructions": (
            "Tap the ball inside to inside twice, drag it back with your sole, "
            "then turn away with the outside of that same foot. Count the "
            "clean ones in 30 seconds."
        ),
        "cue": "Four touches, no stops",
        "score_label": "clean combos",
        "per_foot": True,
        "timer_seconds": 30,
        "medals": (5, 7, 9),
        "order": 205,
    },
    # --- Rebounder ---------------------------------------------------------
    # First touch and passing. The research's best tool is a wall; the
    # rebounder is the same job with a ball that comes back at him.
    {
        "slug": "rebounder-two-touch",
        "name": "Two-touch passes",
        "pack": Card.REBOUNDER,
        "instructions": (
            "Pass into the rebounder, control it with one touch and pass it "
            "back with the next. Count clean passes in 60 seconds, weak foot "
            "first, then strong."
        ),
        "cue": "Touch, pass, touch, pass",
        "score_label": "passes",
        "per_foot": True,
        "timer_seconds": 60,
        "medals": (25, 32, 40),
        "order": 400,
        "needs_rebounder": True,
    },
    {
        "slug": "rebounder-one-touch",
        "name": "One-touch passes",
        "pack": Card.REBOUNDER,
        "instructions": (
            "Pass into the rebounder and hit it straight back without stopping "
            "it. Count clean passes in 60 seconds, weak foot first, then "
            "strong."
        ),
        "cue": "Keep it on the floor",
        "score_label": "passes",
        "per_foot": True,
        "timer_seconds": 60,
        "medals": (30, 40, 50),
        "order": 401,
        "needs_rebounder": True,
    },
    {
        "slug": "rebounder-turn",
        "name": "Receive and turn",
        "pack": Card.REBOUNDER,
        "instructions": (
            "Pass into the rebounder. As it comes back, turn with your first "
            "touch so you face away from it, then dribble out. Ten goes with "
            "each foot, and count the turns that took one touch."
        ),
        "cue": "One touch and you're facing away",
        "score_label": "one-touch turns",
        "per_foot": True,
        "out_of": 10,
        "medals": (6, 8, 10),
        "order": 402,
        "needs_rebounder": True,
    },
    {
        "slug": "rebounder-into-space",
        "name": "Touch it into space",
        "pack": Card.REBOUNDER,
        "instructions": (
            "Put a cone a few steps to the side. Pass into the rebounder and "
            "take your first touch towards the cone, so you are moving as you "
            "control it. Ten goes with each foot, and count the touches that "
            "reach the cone."
        ),
        "cue": "Touch it where you're going",
        "score_label": "touches to the cone",
        "per_foot": True,
        "out_of": 10,
        "medals": (6, 8, 10),
        "order": 403,
        "needs_rebounder": True,
        "needs_cones": True,
    },
    {
        "slug": "rebounder-cushion",
        "name": "Catch the egg",
        "pack": Card.REBOUNDER,
        "instructions": (
            "Throw the ball into the rebounder so it comes back in the air. "
            "Kill it dead with one touch, so it drops at your feet and stays "
            "there. Ten goes with each foot."
        ),
        "cue": "Don't break the egg",
        "score_label": "dead balls",
        "per_foot": True,
        "out_of": 10,
        "medals": (5, 7, 9),
        "order": 404,
        "needs_rebounder": True,
    },
    # --- Dribbling ---------------------------------------------------------
    {
        "slug": "slalom-race",
        "name": "Slalom race",
        "pack": Card.DRIBBLING,
        "instructions": (
            "Put six cones in a line, one big step apart. Dribble in and out "
            "of them, round the last one and back again. Use the clock to time "
            "it."
        ),
        "cue": "Fast, and every cone",
        "scoring": Card.TIME,
        "score_label": "seconds, there and back",
        "medals": (140, 120, 100),
        "order": 500,
        "needs_cones": True,
    },
    {
        "slug": "speed-dribble-race",
        "name": "Speed dribble race",
        "pack": Card.DRIBBLING,
        "instructions": (
            "Put two cones fifteen big steps apart. Dribble to the far one as "
            "fast as you can, round it and back. The ball has to stay close "
            "enough to stop."
        ),
        "cue": "Fast, but still yours",
        "scoring": Card.TIME,
        "score_label": "seconds, there and back",
        "medals": (120, 100, 85),
        "order": 501,
        "needs_cones": True,
    },
    {
        "slug": "slow-slow-fast",
        "name": "Slow, slow, fast",
        "pack": Card.DRIBBLING,
        "instructions": (
            "Put a cone ten big steps away. Dribble slowly at it, then burst "
            "past it as fast as you can for four steps. Eight goes, and count "
            "the ones where the burst really surprised the cone."
        ),
        "cue": "Slow, then GO",
        "score_label": "real bursts",
        "out_of": 8,
        "medals": (5, 6, 7),
        "order": 502,
        "needs_cones": True,
    },
    # --- Finishing ---------------------------------------------------------
    {
        "slug": "corners",
        "name": "Pick your corner",
        "pack": Card.FINISHING,
        "instructions": (
            "Put a cone in each bottom corner of the goal. Before every shot, "
            "say out loud which corner. Five shots with each foot, and count "
            "the ones that go in the corner you said."
        ),
        "cue": "Decide, then place it",
        "score_label": "corners hit",
        "per_foot": True,
        "out_of": 5,
        "medals": (2, 3, 4),
        "order": 600,
        "needs_goal": True,
        "needs_cones": True,
    },
    {
        "slug": "laces-rolling",
        "name": "Laces on the move",
        "pack": Card.FINISHING,
        "instructions": (
            "Roll the ball out in front of you, chase it and strike it with "
            "your laces before it stops. Five with each foot, and count the "
            "ones on target."
        ),
        "cue": "Hit the middle of the ball",
        "score_label": "on target",
        "per_foot": True,
        "out_of": 5,
        "medals": (3, 4, 5),
        "order": 601,
        "needs_goal": True,
    },
    {
        "slug": "rebounder-finish",
        "name": "Set and finish",
        "pack": Card.FINISHING,
        "instructions": (
            "Pass into the rebounder, take one touch to set it, then shoot. "
            "Five with each foot, and count your goals."
        ),
        "cue": "Set it, then pick a spot",
        "score_label": "goals",
        "per_foot": True,
        "out_of": 5,
        "medals": (2, 3, 4),
        "order": 602,
        "needs_goal": True,
        "needs_rebounder": True,
    },
    {
        "slug": "volley-finish",
        "name": "Volley it in",
        "pack": Card.FINISHING,
        "instructions": (
            "Throw the ball up for yourself and volley it at the goal before it "
            "bounces, or just after. Five with each foot, and count your goals."
        ),
        "cue": "Keep it under the bar",
        "score_label": "goals",
        "per_foot": True,
        "out_of": 5,
        "medals": (2, 3, 4),
        "order": 603,
        "needs_goal": True,
    },
    # --- Keepy-ups ---------------------------------------------------------
    # A challenge, not a pillar: the research rates it for touch and fun, and
    # not much for the game. So it is in the deck and nothing requires it.
    {
        "slug": "keepy-ups-best",
        "name": "Keepy-up record",
        "pack": Card.KEEPY_UPS,
        "instructions": (
            "Juggle any way you like, feet, thighs or head. Have three goes "
            "and put in your best run."
        ),
        "cue": "Beat your best",
        "score_label": "keepy-ups",
        "medals": (30, 50, 100),
        "order": 700,
    },
    {
        "slug": "keepy-ups-weak",
        "name": "Weak foot keepy-ups",
        "pack": Card.KEEPY_UPS,
        "instructions": (
            "Juggle with your weak foot only. Have three goes and put in your "
            "best run."
        ),
        "cue": "Weak foot only",
        "score_label": "keepy-ups",
        "medals": (10, 20, 35),
        "order": 701,
    },
    {
        "slug": "keepy-ups-alternate",
        "name": "Left, right, left, right",
        "pack": Card.KEEPY_UPS,
        "instructions": (
            "Juggle swapping feet every single touch. Have three goes and put "
            "in your best run."
        ),
        "cue": "Every other touch, weak foot",
        "score_label": "keepy-ups",
        "medals": (10, 20, 40),
        "order": 702,
    },
    {
        "slug": "keepy-ups-thighs",
        "name": "Thigh keepy-ups",
        "pack": Card.KEEPY_UPS,
        "instructions": (
            "Juggle with your thighs only, swapping legs each time. Have three "
            "goes and put in your best run."
        ),
        "cue": "Flat as a table",
        "score_label": "keepy-ups",
        "medals": (10, 20, 30),
        "order": 703,
    },
    # --- Free play ---------------------------------------------------------
    # The research's strongest finding is that the players who made it played
    # more, not drilled more. A kickabout counts.
    {
        "slug": "free-play",
        "name": "I played football",
        "pack": Card.FREE_PLAY,
        "instructions": (
            "A kickabout in the garden, the park or the street. A 1v1 with "
            "Dad. Anything with a ball that was not on a card counts."
        ),
        "cue": "Play counts",
        "scoring": Card.NONE,
        "order": 900,
    },
] + _move_cards()

# Slugs switched off but kept, so his plays against them survive. Empty for
# now; add to it rather than taking a card out of CARDS.
RETIRED = set()


def seed_deck():
    """Write every card in CARDS. Safe to re-run; deletes nothing."""
    for card in CARDS:
        fields = dict(card)
        slug = fields.pop("slug")
        bronze, silver, gold = fields.pop("medals", (None, None, None))
        defaults = {
            "scoring": Card.COUNT,
            "per_foot": False,
            "out_of": None,
            "timer_seconds": None,
            "move": "",
            "level": None,
            "needs_cones": False,
            "needs_rebounder": False,
            "needs_goal": False,
            "score_label": "",
            **fields,
            "bronze": bronze,
            "silver": silver,
            "gold": gold,
            "is_active": slug not in RETIRED,
        }
        Card.objects.update_or_create(slug=slug, defaults=defaults)
