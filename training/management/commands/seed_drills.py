"""Create the starter drill library, the weekly plan, the badges and Will's
profile.

Coaching principles baked into this data, for a 9-year-old in academy football:

* Ball mastery and first touch are the priority. Technique over fitness.
* Every drill is doable alone, in a garden or a park, with a ball, a wall and a
  few cones. A wall does the job of a passing partner.
* Both feet feature everywhere, and every session has explicit weak-foot work.
* Short speed work is in - accelerations, a first touch and a burst after it,
  a dribble at full pelt. No weights, no plyometrics, no distance running.
* Every session includes juggling. Keepy-ups are the drill he will do for
  the fun of it, and they are pure first touch.
* Nothing lasts longer than five minutes. Each session is a warm-up, four
  technical drills and a fun finisher, and lands on exactly 30 minutes.
* One day off a week. Recovery is part of the plan, not a failure of it.
* Instructions are written for Will to read himself.

Re-running is safe: everything keys off a slug and updates in place.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from training.models import (
    Badge,
    Drill,
    PlanDay,
    PlanDrill,
    Skill,
    TrainingPlan,
)

DEFAULT_PIN = "1234"

# Fixed slot order. These seven hues are validated for colour-blind separation
# against the app's white surface - see the README before changing them.
SKILLS = [
    ("ball-mastery", "Ball mastery", "⚽", "#2a78d6", 1),
    ("dribbling", "Dribbling", "\U0001f3c3", "#eb6834", 2),
    ("passing", "Passing", "\U0001f3af", "#1baf7a", 3),
    ("shooting", "Shooting", "\U0001f945", "#eda100", 4),
    ("first-touch", "First touch", "✨", "#e87ba4", 5),
    ("one-v-one", "1v1", "⚔️", "#4a3aa7", 6),
    ("speed", "Speed", "⚡", "#a32c3f", 7),
]

# (slug, name, skill, instructions, cue, minutes, reps, equipment, difficulty,
#  weak_foot, is_fun)
# equipment is a string of letters: b=ball w=wall c=cones s=space
DRILLS = [
    # --- Ball mastery ----------------------------------------------------
    (
        "toe-taps",
        "Toe taps",
        "ball-mastery",
        "Tap the top of the ball with the bottom of your toes, swapping feet "
        "every time. Stay on your toes and keep the taps small and quick. "
        "Count how many you can do without the ball rolling away.",
        "Quick feet, light touches",
        5, None, "b", 1, False, False,
    ),
    (
        "sole-rolls",
        "Sole rolls",
        "ball-mastery",
        "Put the sole of your foot on top of the ball and roll it across your "
        "body, then stop it with the other foot and roll it back. Keep the "
        "ball in front of you the whole time. Do it slowly first, then speed up.",
        "Roll it, don't kick it",
        5, None, "b", 1, False, False,
    ),
    (
        "foundations",
        "Foundations",
        "ball-mastery",
        "Tap the ball from the inside of one foot to the inside of the other, "
        "like it is bouncing between two walls. Keep your knees bent and your "
        "feet moving. Try to get faster without losing control.",
        "Inside, inside, inside",
        5, None, "b", 1, False, False,
    ),
    (
        "rollovers",
        "Rollovers",
        "ball-mastery",
        "Roll your foot over the top of the ball from one side to the other, "
        "then do the same with your other foot. Do ten with your right, then "
        "ten with your left. Your weaker foot will feel funny at first - that "
        "is exactly why you are doing it.",
        "Both feet, same number",
        5, None, "b", 2, True, False,
    ),
    (
        "figure-eight-legs",
        "Figure of eight",
        "ball-mastery",
        "Roll the ball in a figure of eight around and between your feet, using "
        "the inside of each foot to push it. Keep it tight so the ball never "
        "gets away from you. Look up every few touches.",
        "Tight to your feet",
        5, None, "b", 2, False, False,
    ),
    (
        "weak-foot-taps",
        "Weak foot taps",
        "ball-mastery",
        "Use only your weaker foot. Tap the top of the ball, then roll it a "
        "little way and tap it again. It will feel clumsy - keep going anyway, "
        "because this is how the weak foot catches up.",
        "Only your weak foot",
        5, None, "b", 1, True, False,
    ),
    (
        "freestyle-five",
        "Freestyle time",
        "ball-mastery",
        "Five minutes of anything you like with the ball. Try a trick you saw "
        "on telly, or make one up. There is no wrong way to do this one.",
        "Have fun with it",
        5, None, "b s", 1, False, True,
    ),
    # --- First touch -----------------------------------------------------
    (
        "wall-control-inside",
        "Wall control",
        "first-touch",
        "Pass the ball against the wall, then stop it dead with the inside of "
        "your foot. Take one touch to control it and one to pass it back. Swap "
        "feet every five goes.",
        "Kill it dead",
        5, None, "b w", 1, False, False,
    ),
    (
        "cushion-touch",
        "Cushion your touch",
        "first-touch",
        "Throw the ball at the wall so it comes back in the air. As it arrives, "
        "pull your foot back slightly so the ball drops softly instead of "
        "bouncing off you. Imagine catching an egg without breaking it.",
        "Soft foot, catch the egg",
        5, None, "b w", 2, False, False,
    ),
    (
        "thigh-control",
        "Thigh control",
        "first-touch",
        "Throw the ball up, let it drop onto your thigh, and cushion it so it "
        "lands gently in front of you. Do five on your right thigh, then five "
        "on your left.",
        "Relax your leg",
        5, None, "b", 2, False, False,
    ),
    (
        "first-touch-turn",
        "First touch and turn",
        "first-touch",
        "Pass the ball to the wall, then as it comes back take your first touch "
        "sideways so you end up facing the other way. Do it both ways: turning "
        "left and turning right. The turn should take one touch, not three.",
        "One touch, then you're gone",
        5, None, "b w s", 3, True, False,
    ),
    (
        "weak-foot-control",
        "Weak foot control",
        "first-touch",
        "Pass to the wall with your weaker foot and control it with your weaker "
        "foot too. Do not cheat and use your good foot. Twenty passes, all weak "
        "foot.",
        "Weak foot only",
        5, None, "b w", 2, True, False,
    ),
    (
        "control-and-move",
        "Control and move away",
        "first-touch",
        "Put a cone a few steps to your side. Pass to the wall, then take your "
        "first touch towards the cone so you are moving as you control it. A "
        "good first touch takes you somewhere.",
        "Touch it where you're going",
        5, None, "b w c", 2, False, False,
    ),
    (
        "bouncing-control",
        "Kill a bouncing ball",
        "first-touch",
        "Throw the ball high against the wall so it bounces back awkwardly. "
        "Whatever way it comes, get it under control in two touches. Use your "
        "foot, thigh or chest, whichever fits.",
        "Two touches, ball is yours",
        5, None, "b w", 3, False, False,
    ),
    (
        "juggling-laces",
        "Juggling with your laces",
        "first-touch",
        "Drop the ball onto your laces and juggle it, keeping your ankle locked "
        "and your toes pointing up. Every keepy-up counts, even the scruffy "
        "ones. Beat your best from last time.",
        "Toes up, ankle locked",
        None, 30, "b", 2, False, True,
    ),
    (
        "thigh-juggles",
        "Thigh juggles",
        "first-touch",
        "Juggle the ball using only your thighs, swapping legs each time. Keep "
        "your thigh flat like a table top. Count them out loud.",
        "Flat as a table",
        None, 20, "b", 2, False, True,
    ),
    (
        "weak-foot-juggles",
        "Weak foot juggles",
        "first-touch",
        "Juggle using only your weaker foot. This is hard and you will drop it "
        "a lot - that is normal. Fifteen in a row is a brilliant score.",
        "Weak foot only",
        None, 15, "b", 3, True, True,
    ),
    (
        "keepy-up-record",
        "Beat your keepy-up record",
        "first-touch",
        "Juggle the ball any way you like - feet, thighs, head - and count your "
        "best run. Write the number down and try to beat it next week.",
        "Beat your best",
        5, None, "b", 2, False, True,
    ),
    (
        "juggle-and-catch",
        "Juggle and catch",
        "first-touch",
        "Drop the ball onto your foot, flick it up once, then catch it. When "
        "one is easy, catch it after two flicks, then three. Every juggler "
        "starts here.",
        "One more than last time",
        None, 25, "b", 1, False, False,
    ),
    (
        "alternate-foot-juggles",
        "Left, right, left, right",
        "first-touch",
        "Juggle swapping feet every single touch - left, right, left, right. "
        "Your weaker foot gets exactly as many goes as your good one, which is "
        "the whole point. Count out loud as you go.",
        "Every other touch, weak foot",
        None, 20, "b", 2, True, False,
    ),
    (
        "low-juggles",
        "Low juggles",
        "first-touch",
        "Juggle keeping the ball below your knee, with tiny soft touches. Low "
        "and slow is much harder than big bouncy ones, and it is what teaches "
        "your feet to be gentle. See how long you can keep it small.",
        "Small touches, ball stays low",
        None, 20, "b", 2, False, False,
    ),
    (
        "juggle-and-volley",
        "Juggle and volley",
        "first-touch",
        "Juggle the ball a few times, then volley it against the wall out of "
        "the air. Collect the rebound and start again. Do five finishing with "
        "your right foot and five with your left.",
        "Watch it onto your laces",
        5, None, "b w s", 3, False, True,
    ),
    (
        "around-the-world",
        "Around the world",
        "first-touch",
        "Flick the ball up and swing your foot all the way around it before you "
        "touch it again. You will miss loads at first and that is fine - it is "
        "a showing-off trick. Land one and you have earned bragging rights.",
        "Big swing, then catch it",
        5, None, "b s", 3, False, True,
    ),
    # --- Dribbling -------------------------------------------------------
    (
        "cone-slalom",
        "Cone slalom",
        "dribbling",
        "Put four or five cones in a line, about two steps apart. Dribble in "
        "and out of them with little touches, then turn at the end and come "
        "back. Use both feet - the outside of one, the inside of the other.",
        "Little touches, head up",
        5, None, "b c s", 1, False, False,
    ),
    (
        "figure-eight-dribble",
        "Figure of eight dribbling",
        "dribbling",
        "Put two cones about four steps apart and dribble a figure of eight "
        "around them. Go slowly and keep the ball close, then speed up when it "
        "feels easy. Change direction with the outside of your foot.",
        "Ball never leaves you",
        5, None, "b c s", 2, False, False,
    ),
    (
        "drag-backs",
        "Drag backs",
        "dribbling",
        "Put your foot on top of the ball and drag it back towards you, then "
        "push it forward again. Do ten with your right foot, then ten with your "
        "left. Keep your head up and look forward, not down at the ball.",
        "Head up, sole on top",
        5, None, "b s", 1, True, False,
    ),
    (
        "cruyff-turn",
        "Cruyff turn",
        "dribbling",
        "Pretend you are about to pass the ball, then instead drag it behind "
        "your standing leg with the inside of your foot and spin away. Sell the "
        "fake first - the turn only works if the defender believes you. Do it "
        "both ways.",
        "Sell the fake, then go",
        5, None, "b c s", 2, False, False,
    ),
    (
        "step-over",
        "Step over",
        "dribbling",
        "Step your foot over the top of the ball without touching it, then push "
        "the ball away with the outside of your other foot. Practise going both "
        "left and right. Big step over, small touch away.",
        "Big step, small touch",
        5, None, "b c s", 2, False, False,
    ),
    (
        "inside-outside-cuts",
        "Inside and outside cuts",
        "dribbling",
        "Dribble forward, then cut the ball sharply with the inside of your "
        "foot, dribble again and cut it back with the outside. Do a whole set "
        "with your right foot, then a whole set with your left.",
        "Sharp cut, then accelerate",
        5, None, "b c s", 2, True, False,
    ),
    # --- Passing ---------------------------------------------------------
    (
        "wall-pass-one-touch",
        "One touch wall passes",
        "passing",
        "Pass the ball against the wall and hit it straight back without "
        "stopping it first. Use the inside of your foot and keep the ball on "
        "the floor. See how many you can string together.",
        "Inside of the foot, low",
        5, None, "b w", 2, False, False,
    ),
    (
        "weak-foot-wall-pass",
        "Weak foot wall passes",
        "passing",
        "Same as one touch passes, but only with your weaker foot. It will feel "
        "wrong and the ball will go everywhere at first. Twenty passes, no "
        "swapping.",
        "Weak foot only",
        5, None, "b w", 2, True, False,
    ),
    (
        "two-touch-wall-pass",
        "Two touch wall passes",
        "passing",
        "Pass to the wall, control it with one touch, then pass it back with "
        "the next. Touch, pass, touch, pass - get a rhythm going. Swap which "
        "foot you use every ten.",
        "Touch, pass, touch, pass",
        5, None, "b w", 1, False, False,
    ),
    (
        "target-passing",
        "Hit the target",
        "passing",
        "Put two cones against the wall to make a small gate, or pick a mark on "
        "the wall. Pass at it from about ten steps back and count your hits out "
        "of twenty. Use both feet.",
        "Pick your spot first",
        None, 40, "b w c", 2, False, False,
    ),
    (
        "driven-pass",
        "Driven pass",
        "passing",
        "Stand further back from the wall and drive the ball with your laces so "
        "it goes hard and stays low. Lean over the ball so it does not balloon "
        "up. Ten with each foot.",
        "Lean over it, keep it down",
        5, None, "b w s", 3, False, False,
    ),
    (
        "wall-target-challenge",
        "Wall target challenge",
        "passing",
        "Pick a small target on the wall and see how many times you can hit it "
        "out of ten. Then try with your other foot and see if you can beat it. "
        "Tell your coach your best score.",
        "Aim small, miss small",
        5, None, "b w", 2, False, True,
    ),
    # --- Shooting --------------------------------------------------------
    (
        "laces-technique",
        "Shooting with your laces",
        "shooting",
        "Strike the middle of the ball with your laces, not your toe. Point "
        "your toes down, lock your ankle, and follow through towards where you "
        "want it to go. Ten with each foot.",
        "Laces, not toes",
        5, None, "b w s", 2, False, False,
    ),
    (
        "corner-placement",
        "Pick your corner",
        "shooting",
        "Put a cone at each bottom corner of your goal or wall. Before every "
        "shot, decide out loud which corner you are aiming for, then use the "
        "inside of your foot to place it there. Accuracy beats power.",
        "Decide, then place it",
        None, 20, "b w c", 2, False, False,
    ),
    (
        "weak-foot-finish",
        "Weak foot finish",
        "shooting",
        "Every shot with your weaker foot. Start close to the wall so you can "
        "get the technique right, then step back a bit. Fifteen shots, no "
        "swapping feet.",
        "Weak foot only",
        5, None, "b w c", 3, True, False,
    ),
    (
        "low-driven-shot",
        "Low driven shot",
        "shooting",
        "Shoot hard and keep the ball under knee height. Lean your body over "
        "the ball as you strike it - leaning back is what sends it over the "
        "bar. Ten with each foot.",
        "Lean over it",
        5, None, "b w s", 2, False, False,
    ),
    (
        "turn-and-shoot",
        "Turn and shoot",
        "shooting",
        "Stand with your back to the wall, roll the ball to yourself, turn "
        "quickly and shoot. Try to do it in two touches - turn, shoot. Both "
        "feet.",
        "Turn quick, shoot early",
        5, None, "b w c", 3, False, False,
    ),
    # --- 1v1 -------------------------------------------------------------
    (
        "step-over-past-cone",
        "Step over past the defender",
        "one-v-one",
        "Put a cone down and pretend it is a defender. Dribble at it, do a step "
        "over, then push the ball past it with the outside of your foot and "
        "sprint three steps. Go past it on both sides.",
        "Explode after the trick",
        5, None, "b c s", 2, False, False,
    ),
    (
        "drag-back-escape",
        "Drag back escape",
        "one-v-one",
        "Dribble at a cone, then drag the ball back and take it away in the "
        "other direction. This is what you do when a defender blocks your way. "
        "Practise escaping with both feet.",
        "Drag it, turn, go",
        5, None, "b c s", 2, True, False,
    ),
    (
        "cruyff-past-cone",
        "Cruyff past the defender",
        "one-v-one",
        "Dribble at a cone, fake a pass, then Cruyff turn away from it and "
        "accelerate. The fake is the important bit - make it look real. Both "
        "directions.",
        "Fake it properly",
        5, None, "b c s", 3, False, False,
    ),
    (
        "change-of-pace",
        "Change of pace",
        "one-v-one",
        "Dribble slowly towards a cone, then burst past it as fast as you can "
        "for three or four steps, then slow down again. Defenders hate it when "
        "you change speed suddenly.",
        "Slow, then GO",
        5, None, "b c s", 2, False, False,
    ),
    # --- Speed -----------------------------------------------------------
    (
        "sprint-to-the-ball",
        "Sprint to the ball",
        "speed",
        "Put the ball about ten steps in front of you and stand up tall. Sprint "
        "at it as fast as you can, then take one soft touch to stop it dead. "
        "Walk back, get your breath, and go again.",
        "Explode, then calm the ball",
        5, None, "b s", 1, False, False,
    ),
    (
        "first-touch-and-go",
        "First touch and go",
        "speed",
        "Pass the ball against the wall, and as it comes back push your first "
        "touch forward and chase it for five quick steps. Do a set with your "
        "right foot, then a set with your left. The touch is what makes the "
        "run work.",
        "Touch forward, then go",
        5, None, "b w s", 2, True, False,
    ),
    (
        "speed-dribble-gate",
        "Speed dribble",
        "speed",
        "Put two cones about fifteen steps apart. Dribble from one to the other "
        "as fast as you can while keeping the ball close enough to stop. Turn "
        "at the cone and come straight back.",
        "Fast feet, ball still yours",
        5, None, "b c s", 2, False, False,
    ),
    (
        "turn-and-sprint",
        "Turn and sprint",
        "speed",
        "Put two cones about ten steps apart and stand at one of them. Sprint "
        "to the other cone, touch the ground beside it, turn and sprint back. "
        "Do five of those and rest properly in between.",
        "Low on the turn",
        5, None, "c s", 1, False, False,
    ),
    (
        "standing-start",
        "Standing starts",
        "speed",
        "Stand still with one foot a little in front of the other, like you are "
        "waiting for the ball to come. Push hard off your back foot and sprint "
        "ten steps, then slow down gently. Rest until you feel ready before the "
        "next one.",
        "First three steps win it",
        5, None, "s", 1, False, False,
    ),
    (
        "beat-the-clock",
        "Beat the clock",
        "speed",
        "Put two cones about ten steps apart and time yourself dribbling down "
        "and back. Write the time down, have a breather, then try to beat it. "
        "Three goes is plenty, because this one is about being quick, not tired.",
        "Beat your own time",
        5, None, "b c s", 2, False, True,
    ),
]

# Juggling and keepy-ups. Every session carries exactly one, so it needs to be
# a flag the plan and the tests can see - the same job weak_foot does. Kept as
# a set of slugs rather than a thirteenth column on fifty tuples.
JUGGLING = {
    "juggling-laces",
    "thigh-juggles",
    "weak-foot-juggles",
    "keepy-up-record",
    "juggle-and-catch",
    "alternate-foot-juggles",
    "low-juggles",
    "juggle-and-volley",
    "around-the-world",
}

# PRESEASON SHAPE: six sessions of exactly 30 minutes, and Sunday off. There is
# no academy and there are no matches over the summer, so Friday and Saturday
# are no longer bonus days. When the season restarts, put is_optional back on
# weekdays 4 and 5 and cut them back down.
#
# Sunday is a real rest day, not a bonus one. A nine-year-old training seven
# days out of seven has nowhere to recover, and the streak - which breaks on a
# missed required day - was pushing him to do it anyway. Rest days are skipped
# by the streak walk entirely, so taking it costs him nothing. That is 180
# minutes a week rather than 210.
#
# Every drill is five minutes, so a day is simply six of them: a ball-mastery
# warm-up on the floor, four technical drills, then a fun finisher. Rep-based
# drills count as five minutes too, so the sum lands on 30 either way and
# rebalancing a day means swapping a drill, not doing arithmetic.
#
# Speed sits on three days - Tuesday, Thursday and Saturday. It is the one
# thing here that tires him rather than teaches him, so it is spaced out and
# never doubled up in a session. Every day still carries explicit weak-foot
# work.
#
# Every day also carries exactly one juggling block, most of them in the fun
# finisher slot at the end. Keepy-ups are the one thing he will keep doing for
# their own sake, and they are pure touch practice - so they are a fixture of
# the session rather than something he might get round to.
PLAN_NAME = "Will's Week"

# Each day carries two running orders and alternates between them, so Monday is
# not the same six drills for six months. The fortnight uses all 50 drills in
# the library; on its own, one week could only ever reach 36 of them.
#
# Both weeks of a given day keep the same shape - the same label, the same
# balance, speed on the same three days - so the balance of the fortnight is
# the balance of either week. Swapping a drill means swapping it for one that
# keeps that balance. Slot 5 on days 0 and 3 is the deliberate exception, below:
# the skill there differs between the weeks, which is why the labels name the
# day's theme rather than listing its skills.
#
# Every session carries at least one shooting or dribbling drill. Those are the
# two things he will do for the fun of it, and a session with neither is a
# session he has to be talked into. Monday and Thursday carry that rule in
# slot 5 - because the other four days already had one - and the two weeks take
# it from opposite ends so neither week doubles a drill up.
#
# Each week is 36 slots and 36 *distinct* drills: that is the whole reason the
# second week exists, and it is what stops a drill landing on back-to-back
# days. Both rules are asserted in test_seed.py. Two slots are load-bearing for
# weak foot - day 3 week A's `weak-foot-finish` and week B's
# `inside-outside-cuts` are the only weak-foot work in their sessions.
#
# (weekday, label, target_minutes, is_rest, is_optional,
#  [week A drills], [week B drills])
PLAN_DAYS = [
    (0, "Ball mastery + first touch", 30, False, False, [
        "foundations", "wall-control-inside", "weak-foot-control",
        "cushion-touch", "drag-backs", "keepy-up-record",
    ], [
        "toe-taps", "thigh-control", "first-touch-turn",
        "bouncing-control", "laces-technique", "weak-foot-juggles",
    ]),
    (1, "Dribbling + speed", 30, False, False, [
        "rollovers", "cone-slalom", "step-over", "speed-dribble-gate",
        "cruyff-past-cone", "around-the-world",
    ], [
        "figure-eight-legs", "cruyff-turn", "drag-backs", "turn-and-sprint",
        "change-of-pace", "keepy-up-record",
    ]),
    (2, "Passing + shooting", 30, False, False, [
        "sole-rolls", "weak-foot-wall-pass", "wall-pass-one-touch",
        "laces-technique", "corner-placement", "juggle-and-volley",
    ], [
        "rollovers", "target-passing", "driven-pass", "weak-foot-finish",
        "low-driven-shot", "juggling-laces",
    ]),
    (3, "First touch + speed", 30, False, False, [
        "figure-eight-legs", "first-touch-turn", "first-touch-and-go",
        "control-and-move", "weak-foot-finish", "juggling-laces",
    ], [
        "foundations", "step-over-past-cone", "sprint-to-the-ball",
        "juggle-and-catch", "inside-outside-cuts", "freestyle-five",
    ]),
    (4, "Dribbling + passing", 30, False, False, [
        "toe-taps", "inside-outside-cuts", "figure-eight-dribble",
        "driven-pass", "target-passing", "thigh-juggles",
    ], [
        "weak-foot-taps", "cone-slalom", "figure-eight-dribble",
        "two-touch-wall-pass", "low-juggles", "wall-target-challenge",
    ]),
    (5, "Shooting + speed", 30, False, False, [
        "weak-foot-taps", "turn-and-shoot", "low-driven-shot",
        "alternate-foot-juggles", "drag-back-escape", "beat-the-clock",
    ], [
        "sole-rolls", "corner-placement", "turn-and-shoot", "standing-start",
        "drag-back-escape", "thigh-juggles",
    ]),
    (6, "Rest day", 0, True, False, [], []),
]

BADGES = [
    ("first-session", "First session", "You did your first drill.", "\U0001f31f",
     Badge.TOTAL_DRILLS, 1, 1),
    ("streak-3", "3 in a row", "Trained three days in a row.", "\U0001f525",
     Badge.STREAK, 3, 2),
    ("streak-7", "Full week", "Trained seven days in a row.", "\U0001f4a5",
     Badge.STREAK, 7, 3),
    ("streak-30", "Month machine", "Thirty days in a row. Unbelievable.",
     "\U0001f680", Badge.STREAK, 30, 4),
    ("drills-10", "10 drills", "Ten drills completed.", "✅",
     Badge.TOTAL_DRILLS, 10, 5),
    ("drills-50", "50 drills", "Fifty drills completed.", "\U0001f3c5",
     Badge.TOTAL_DRILLS, 50, 6),
    ("drills-100", "100 drills", "One hundred drills. Proper dedication.",
     "\U0001f451", Badge.TOTAL_DRILLS, 100, 7),
    ("all-skills", "All rounder", "Tried every single skill category.",
     "\U0001f308", Badge.SKILLS_TRIED, 7, 8),
    ("minutes-500", "500 minutes", "Over eight hours of training.", "⏱️",
     Badge.TOTAL_MINUTES, 500, 9),
    ("weak-foot-25", "Two footed", "Twenty five weak foot drills done.",
     "\U0001f9a6", Badge.WEAK_FOOT, 25, 10),
    ("juggling-25", "Keepy-up king", "Twenty five juggling drills done.",
     "\U0001f939", Badge.JUGGLING, 25, 11),
    # The two at the end are the long game. Everything above is reachable in
    # a month of preseason; these are still there to chase afterwards.
    ("perfect-week", "Perfect week",
     "Every drill, on every training day, for a whole week.",
     "\U0001f48e", Badge.PERFECT_WEEKS, 1, 12),  # not the passing dartboard
    ("streak-100", "Century", "One hundred days in a row.", "\U0001f4af",
     Badge.STREAK, 100, 13),
]


class Command(BaseCommand):
    help = "Create the starter drills, weekly plan, badges and profiles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing drills and plans first, instead of updating them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            PlanDrill.objects.all().delete()
            PlanDay.objects.all().delete()
            TrainingPlan.objects.all().delete()
            Drill.objects.all().delete()
            Skill.objects.all().delete()
            self.stdout.write("Cleared existing drills and plans.")

        skills = self._seed_skills()
        self._seed_drills(skills)
        self._seed_badges()
        self._seed_plan()
        self._seed_profiles()

        self.stdout.write(
            self.style.SUCCESS(
                f"Ready: {Skill.objects.count()} skills, "
                f"{Drill.objects.count()} drills, "
                f"{Badge.objects.count()} badges, "
                f"plan '{PLAN_NAME}' with {PlanDay.objects.count()} days."
            )
        )

    def _seed_skills(self):
        skills = {}
        for slug, name, emoji, colour, order in SKILLS:
            skill, _ = Skill.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "emoji": emoji,
                    "colour": colour,
                    "order": order,
                },
            )
            skills[slug] = skill
        return skills

    def _seed_drills(self, skills):
        for (
            slug, name, skill_slug, instructions, cue, minutes, reps,
            equipment, difficulty, weak_foot, is_fun,
        ) in DRILLS:
            Drill.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "skill": skills[skill_slug],
                    "instructions": instructions,
                    "cue": cue,
                    "duration_minutes": minutes,
                    "target_reps": reps,
                    "needs_ball": "b" in equipment,
                    "needs_wall": "w" in equipment,
                    "needs_cones": "c" in equipment,
                    "needs_space": "s" in equipment,
                    "difficulty": difficulty,
                    "weak_foot": weak_foot,
                    "is_fun": is_fun,
                    "is_juggling": slug in JUGGLING,
                    "is_active": True,
                },
            )

    def _seed_badges(self):
        for code, name, description, emoji, kind, threshold, order in BADGES:
            Badge.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "emoji": emoji,
                    "kind": kind,
                    "threshold": threshold,
                    "order": order,
                },
            )

    def _seed_plan(self):
        plan, _ = TrainingPlan.objects.update_or_create(
            name=PLAN_NAME, defaults={"is_active": True}
        )
        for (
            weekday, label, minutes, is_rest, is_optional, week_a, week_b
        ) in PLAN_DAYS:
            day, _ = PlanDay.objects.update_or_create(
                plan=plan,
                weekday=weekday,
                defaults={
                    "label": label,
                    "target_minutes": minutes,
                    "is_rest": is_rest,
                    "is_optional": is_optional,
                },
            )
            # Rebuild the running order from scratch so re-seeding cannot
            # leave stale or duplicated entries behind.
            day.items.all().delete()
            for week, slugs in ((PlanDrill.WEEK_A, week_a), (PlanDrill.WEEK_B, week_b)):
                for order, slug in enumerate(slugs, start=1):
                    PlanDrill.objects.create(
                        plan_day=day,
                        drill=Drill.objects.get(slug=slug),
                        order=order,
                        week=week,
                    )

    def _seed_profiles(self):
        """Create Will's profile if it is missing.

        One profile only - Dad uses the same code and the same phone. An
        existing account is never touched, so re-seeding will not reset a PIN
        that has been changed. Use `manage.py set_pin` for that.
        """
        User = get_user_model()

        will, created = User.objects.get_or_create(
            username="will", defaults={"first_name": "Will", "is_staff": False}
        )
        if created:
            will.set_password(DEFAULT_PIN)
            will.save()
            self.stdout.write(
                self.style.WARNING(
                    f"Created Will with code {DEFAULT_PIN} - "
                    "change it with: manage.py set_pin will <pin>"
                )
            )
