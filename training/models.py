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
from django.urls import reverse

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

    def get_absolute_url(self):
        return reverse("training:library_skill", args=[self.slug])


class DrillQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


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
    is_active = models.BooleanField(default=True)

    objects = DrillQuerySet.as_manager()

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

    def get_absolute_url(self):
        return reverse("training:drill", args=[self.slug])

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
        """Short label for the Today list, e.g. '5 min' or '50 reps'."""
        if self.is_timed:
            return f"{self.duration_minutes} min"
        return f"{self.target_reps} reps"

    @property
    def equipment(self):
        """List of (emoji, label) pairs for the kit this drill needs."""
        items = []
        if self.needs_ball:
            items.append(("⚽", "Ball"))
        if self.needs_wall:
            items.append(("\U0001f9f1", "Wall"))
        if self.needs_cones:
            items.append(("\U0001f6a9", "Cones"))
        if self.needs_space:
            items.append(("\U0001f333", "Space"))
        return items

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

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            TrainingPlan.objects.exclude(pk=self.pk).update(is_active=False)


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

    @property
    def drills(self):
        return [item.drill for item in self.items.select_related("drill__skill")]

    @property
    def is_required(self):
        """A day Will is expected to train. Drives the streak."""
        return not (self.is_rest or self.is_optional)


class PlanDrill(models.Model):
    """A drill's place in a day's running order."""

    plan_day = models.ForeignKey(PlanDay, on_delete=models.CASCADE, related_name="items")
    drill = models.ForeignKey(Drill, on_delete=models.CASCADE, related_name="plan_uses")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

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
    KIND_CHOICES = [
        (STREAK, "Day streak"),
        (TOTAL_DRILLS, "Drills completed"),
        (SKILLS_TRIED, "Skills tried"),
        (TOTAL_MINUTES, "Minutes trained"),
        (WEAK_FOOT, "Weak foot drills"),
        (JUGGLING, "Juggling drills"),
        (PERFECT_WEEKS, "Perfect weeks"),
    ]

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=40)
    description = models.CharField(max_length=120)
    emoji = models.CharField(max_length=8, default="\U0001f3c5")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    threshold = models.PositiveIntegerField()
    order = models.PositiveSmallIntegerField(default=0)

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
