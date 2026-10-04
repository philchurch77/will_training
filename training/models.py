"""Data model for the training app.

Two people use this: Will (the athlete) and Coach (his dad, staff). Both are
plain django.contrib.auth Users, so sessions, login_required and the admin all
come for free. The 4-digit PIN is stored as the password hash.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

WEEKDAYS = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]

DIFFICULTY_CHOICES = [
    (1, "Easy"),
    (2, "Medium"),
    (3, "Hard"),
]

RATING_CHOICES = [
    (1, "Really hard"),
    (2, "Hard"),
    (3, "OK"),
    (4, "Good"),
    (5, "Easy"),
]


def get_athlete():
    """Return the child's user account.

    There is exactly one athlete (Will) and one staff account (Coach). Looking
    the athlete up by is_staff=False avoids hardcoding a primary key, so the
    coach screens keep working if the database is rebuilt from scratch.
    """
    return get_user_model().objects.filter(is_staff=False).order_by("pk").first()


class Skill(models.Model):
    """A category of football skill, e.g. Ball mastery."""

    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=40, unique=True)
    emoji = models.CharField(
        max_length=8, default="⚽", help_text="Shown next to the skill name."
    )
    colour = models.CharField(
        max_length=7, default="#2a78d6", help_text="Hex colour for progress bars."
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Drill(models.Model):
    """One thing Will can do alone with a ball, a wall and a few cones."""

    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=60, unique=True)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="drills")

    instructions = models.TextField(
        help_text="Two or three short sentences, written for Will to read himself."
    )
    cue = models.CharField(max_length=60, help_text="One coaching cue, e.g. 'head up'.")

    # A drill is measured either in minutes or in reps, never both. The
    # constraint below enforces that at the database level.
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    target_reps = models.PositiveSmallIntegerField(null=True, blank=True)

    needs_ball = models.BooleanField(default=True)
    needs_wall = models.BooleanField(default=False)
    needs_cones = models.BooleanField(default=False)
    needs_space = models.BooleanField(default=False)

    difficulty = models.PositiveSmallIntegerField(choices=DIFFICULTY_CHOICES, default=1)
    weak_foot = models.BooleanField(
        default=False, help_text="Explicitly works the weaker foot."
    )
    is_fun = models.BooleanField(
        default=False, help_text="A fun finisher or freestyle drill."
    )
    is_juggling = models.BooleanField(
        default=False, help_text="Juggling or keepy-ups. Every session has one."
    )
    is_combination = models.BooleanField(
        default=False,
        help_text="A sequence of moves joined together, not one move repeated.",
    )
    is_active = models.BooleanField(default=True)


    class Meta:
        ordering = ["skill__order", "difficulty", "name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(duration_minutes__isnull=False, target_reps__isnull=True)
                    | models.Q(duration_minutes__isnull=True, target_reps__isnull=False)
                ),
                name="drill_has_duration_or_reps_not_both",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if (self.duration_minutes is None) == (self.target_reps is None):
            raise ValidationError(
                "Set either a duration in minutes or a target number of reps, "
                "but not both."
            )

    @property
    def is_timed(self):
        return self.duration_minutes is not None

    @property
    def target_label(self):
        """Short label, e.g. '5 min' or '50 reps'.

        Admin only since the plan was retired (leg 3d).
        """
        if self.is_timed:
            return f"{self.duration_minutes} min"
        return f"{self.target_reps} reps"

    @property
    def estimated_minutes(self):
        """Minutes this drill contributes to a session.

        Rep-based drills have no clock, so they count as a flat 5 minutes for
        planning and for the minutes-per-skill chart.
        """
        return self.duration_minutes if self.is_timed else 5


class TrainingPlan(models.Model):
    """A named weekly plan. Exactly one is active at a time."""

    name = models.CharField(max_length=60)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return self.name


class PlanDay(models.Model):
    """One day of the week within a plan."""

    plan = models.ForeignKey(TrainingPlan, on_delete=models.CASCADE, related_name="days")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    label = models.CharField(max_length=60)
    is_rest = models.BooleanField(default=False)
    is_optional = models.BooleanField(
        default=False,
        help_text="Academy or match day - the session is a bonus, not expected.",
    )
    target_minutes = models.PositiveSmallIntegerField(default=30)

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "weekday"], name="one_planday_per_weekday"
            )
        ]

    def __str__(self):
        return f"{self.get_weekday_display()} - {self.label}"


class PlanDrill(models.Model):
    """A drill's place in a day's running order.

    A day holds two running orders, not one. `week` says which half of the
    fortnight this drill belongs to, so Monday alternates between two sessions
    instead of being the same six drills for six months. EVERY_WEEK is for a
    drill that should be a fixture whichever week it is.
    """

    EVERY_WEEK = 0
    WEEK_A = 1
    WEEK_B = 2
    WEEK_CHOICES = [
        (EVERY_WEEK, "Every week"),
        (WEEK_A, "Week A"),
        (WEEK_B, "Week B"),
    ]

    plan_day = models.ForeignKey(PlanDay, on_delete=models.CASCADE, related_name="items")
    drill = models.ForeignKey(Drill, on_delete=models.CASCADE, related_name="plan_uses")
    order = models.PositiveSmallIntegerField(default=0)
    week = models.PositiveSmallIntegerField(
        choices=WEEK_CHOICES,
        default=EVERY_WEEK,
        help_text="Which week of the fortnight this drill is part of.",
    )

    class Meta:
        ordering = ["week", "order", "pk"]

    def __str__(self):
        return f"{self.plan_day} #{self.order}: {self.drill}"


class SessionLog(models.Model):
    """A record that Will did a drill on a given day."""

    athlete = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="session_logs"
    )
    date = models.DateField()
    drill = models.ForeignKey(Drill, on_delete=models.CASCADE, related_name="logs")
    completed = models.BooleanField(default=True)
    actual_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    actual_reps = models.PositiveSmallIntegerField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=RATING_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="How did that feel?",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            # One row per drill per day. This makes completion idempotent, so a
            # completion queued offline can be replayed safely on reconnect.
            models.UniqueConstraint(
                fields=["athlete", "date", "drill"], name="one_log_per_drill_per_day"
            )
        ]

    def __str__(self):
        return f"{self.date} {self.drill}"

    @property
    def minutes_counted(self):
        if self.actual_minutes:
            return self.actual_minutes
        return self.drill.estimated_minutes


class SessionClock(models.Model):
    """How long the whole session actually took, on one day.

    The drills themselves are no longer timed. Will starts one clock, works
    through the six drills at whatever pace he likes - lingering on the ones he
    is enjoying - and the clock is what says how long he trained. Ticking a
    drill and finishing the session both post the elapsed seconds, and the
    saved value only ever goes up, so replaying a stale value from the offline
    queue cannot shrink a session that has since run on.

    Days before this existed have no row here, and progress.py falls back to
    the old sum-of-drill-estimates for them. That is deliberate: his history
    keeps the totals it has always had.
    """

    # A garden session that claims to be longer than this is a phone left
    # running on the kitchen table, not training.
    MAX_SECONDS = 3 * 60 * 60

    athlete = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="session_clocks",
    )
    date = models.DateField()
    seconds = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "date"], name="one_clock_per_day"
            )
        ]

    def __str__(self):
        return f"{self.date} ({self.minutes} min)"

    @property
    def minutes(self):
        """Whole minutes, rounded. Anything under 30 seconds is not a session."""
        return round(self.seconds / 60)


class Badge(models.Model):
    """A milestone Will can earn."""

    STREAK = "streak"
    TOTAL_DRILLS = "total_drills"
    SKILLS_TRIED = "skills_tried"
    TOTAL_MINUTES = "total_minutes"
    WEAK_FOOT = "weak_foot"
    JUGGLING = "juggling"
    PERFECT_WEEKS = "perfect_weeks"
    # The deck's badges (leg 2b). Worked out on the server from Play rows by
    # deck_rules.deck_badge_values and awarded at sync. Shown with every other
    # badge on the Progress tab.
    GOAL_WEEKS_RUN = "goal_weeks_run"
    GOAL_WEEKS_TOTAL = "goal_weeks_total"
    MOVE_GOLDS = "move_golds"
    PERSONAL_BESTS = "personal_bests"
    TEST_WEEKS = "test_weeks"
    WEAK_FOOT_CLOSER = "weak_foot_closer"
    FREE_PLAYS = "free_plays"
    KIND_CHOICES = [
        (STREAK, "Day streak"),
        (TOTAL_DRILLS, "Drills completed"),
        (SKILLS_TRIED, "Skills tried"),
        (TOTAL_MINUTES, "Minutes trained"),
        (WEAK_FOOT, "Weak foot drills"),
        (JUGGLING, "Juggling drills"),
        (PERFECT_WEEKS, "Perfect weeks"),
        (GOAL_WEEKS_RUN, "Goal weeks in a row"),
        (GOAL_WEEKS_TOTAL, "Goal weeks in total"),
        (MOVE_GOLDS, "Move golds"),
        (PERSONAL_BESTS, "Personal bests"),
        (TEST_WEEKS, "Test weeks done"),
        (WEAK_FOOT_CLOSER, "Weak foot closer"),
        (FREE_PLAYS, "Free play"),
    ]
    DECK_KINDS = frozenset({
        GOAL_WEEKS_RUN, GOAL_WEEKS_TOTAL, MOVE_GOLDS, PERSONAL_BESTS,
        TEST_WEEKS, WEAK_FOOT_CLOSER, FREE_PLAYS,
    })
    # The old badges kept through the switch-over (leg 3b). They count old
    # ticks and card plays together - progress.kept_badge_values is the one
    # place that adds them up - and a deck sync awards them.
    KEPT_KINDS = frozenset({TOTAL_DRILLS, SKILLS_TRIED, WEAK_FOOT, JUGGLING})

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=40)
    description = models.CharField(max_length=120)
    emoji = models.CharField(max_length=8, default="\U0001f3c5")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    threshold = models.PositiveIntegerField()
    order = models.PositiveSmallIntegerField(default=0)
    # A badge is retired, never deleted: EarnedBadge.badge is CASCADE, so a
    # delete takes his award with it. A retired badge is never awarded again,
    # and one he already earned stays on his record tagged Legend. Set from
    # RETIRED_BADGES in seed_drills.py.
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "threshold"]

    def __str__(self):
        return self.name


class EarnedBadge(models.Model):
    athlete = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="earned_by")
    earned_on = models.DateField()

    class Meta:
        ordering = ["-earned_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "badge"], name="one_award_per_badge"
            )
        ]

    def __str__(self):
        return f"{self.badge} ({self.earned_on})"


# --- The deck -------------------------------------------------------------
#
# The deck replaces the fixed weekly plan with challenge cards he picks from.
# It is built alongside the plan rather than on top of it: nothing below
# touches a Drill, a SessionLog or a badge, so the old screens keep working
# until the switch-over, and his history is never at risk from this code.
# See docs/chart/deck.md for the legs and CONTEXT.md for the words.


class CardQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Card(models.Model):
    """One challenge with a score, e.g. toe taps in 30 seconds.

    Cards are retired, never deleted, for the same reason drills are: a Play
    points at its card, and his scores are what the record is made of. The
    FK on Play is PROTECT, so a delete fails loudly instead of cascading.
    """

    QUICK_FEET = "quick-feet"
    COMBOS = "combos"
    MOVES = "moves"
    REBOUNDER = "rebounder"
    DRIBBLING = "dribbling"
    FINISHING = "finishing"
    KEEPY_UPS = "keepy-ups"
    FREE_PLAY = "free-play"
    PACK_CHOICES = [
        (QUICK_FEET, "Quick feet"),
        (COMBOS, "Combos"),
        (MOVES, "Moves"),
        (REBOUNDER, "Rebounder"),
        (DRIBBLING, "Dribbling"),
        (FINISHING, "Finishing"),
        (KEEPY_UPS, "Keepy-ups"),
        (FREE_PLAY, "Free play"),
    ]

    # How a score is read. COUNT: more is better. TIME: tenths of a second on
    # the card's own stopwatch, less is better. NONE: free play, no score.
    COUNT = "count"
    TIME = "time"
    NONE = "none"
    SCORING_CHOICES = [(COUNT, "Count"), (TIME, "Time"), (NONE, "No score")]

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=60)
    pack = models.CharField(max_length=20, choices=PACK_CHOICES)
    instructions = models.TextField(
        help_text="Two or three short sentences, written for Will to read himself."
    )
    cue = models.CharField(
        max_length=60, help_text="One cue about the result, not the body."
    )

    scoring = models.CharField(max_length=8, choices=SCORING_CHOICES, default=COUNT)
    score_label = models.CharField(
        max_length=60, blank=True, help_text="What the number means, e.g. 'taps'."
    )
    per_foot = models.BooleanField(
        default=False, help_text="Scored weak foot first, then strong foot."
    )
    out_of = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="The most he can score, if there is one."
    )
    timer_seconds = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Length of a 'how many in N seconds' go."
    )

    # Medal targets. For a TIME card they are tenths of a second and gold is
    # the smallest; for a COUNT card gold is the largest.
    bronze = models.PositiveIntegerField(null=True, blank=True)
    silver = models.PositiveIntegerField(null=True, blank=True)
    gold = models.PositiveIntegerField(null=True, blank=True)

    # A move climbs three levels: on the spot, through the cones, past the
    # cone at full pace. Blank for every card that is not a level of a move.
    move = models.CharField(max_length=40, blank=True)
    level = models.PositiveSmallIntegerField(null=True, blank=True)

    needs_cones = models.BooleanField(default=False)
    needs_rebounder = models.BooleanField(default=False)
    needs_goal = models.BooleanField(default=False)

    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = CardQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Play(models.Model):
    """One go at a card, with whatever he scored.

    The id is made on his phone, not here, because the phone is where a play
    happens: it is saved there first, with or without signal, and sent when
    there is some. Sending the same play twice finds the id already taken and
    changes nothing, which is what makes the sync safe to repeat.
    """

    id = models.UUIDField(primary_key=True, editable=False)
    athlete = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="plays"
    )
    card = models.ForeignKey(Card, on_delete=models.PROTECT, related_name="plays")
    date = models.DateField()
    played_at = models.DateTimeField(help_text="When the phone says it happened.")
    # For a per-foot card, score is the strong foot and weak_score the weak.
    score = models.PositiveIntegerField(null=True, blank=True)
    weak_score = models.PositiveIntegerField(null=True, blank=True)

    # The stamp: what this play was worth in the game, worked out once on the
    # phone when he saved it and never again (deck_rules.py has the numbers).
    # Totals, levels and unlocks add these up, so a later change to points or
    # medal targets can never take back what he earned. Null is a play saved
    # before the game layer, or by an old cached page, and is worth nothing.
    NO_MEDAL, BRONZE, SILVER, GOLD = 0, 1, 2, 3
    MEDAL_CHOICES = [(NO_MEDAL, "None"), (BRONZE, "Bronze"), (SILVER, "Silver"), (GOLD, "Gold")]
    points = models.PositiveSmallIntegerField(null=True, blank=True)
    medal = models.PositiveSmallIntegerField(null=True, blank=True, choices=MEDAL_CHOICES)
    bests = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Feet that beat his best (0-2); a first score is not one."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-played_at"]

    def __str__(self):
        return f"{self.date} {self.card}"
