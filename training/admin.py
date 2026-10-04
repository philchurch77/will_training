from django.contrib import admin

from .models import (
    Badge,
    Card,
    Drill,
    EarnedBadge,
    PlanDay,
    PlanDrill,
    Play,
    SessionLog,
    Skill,
    TrainingPlan,
)


class NoDeleteMixin:
    """Deleting here would take Will's logged history with it.

    `Drill.skill` and `SessionLog.drill` are both CASCADE, so deleting one
    skill in the admin removes every drill under it and every session he ever
    logged against them - his minutes, his streak and the counts behind his
    badges - from a bulk action and one confirmation page. There is no undo
    and nothing to type back in.

    Retiring is the supported way to take a drill out of circulation: add its
    slug to RETIRED in seed_drills.py, which sets is_active=False and leaves
    the row, and his history, alone.
    """

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Skill)
class SkillAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("name", "emoji", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Drill)
class DrillAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("name", "skill", "target_label", "difficulty", "weak_foot", "is_fun")
    list_filter = (
        "skill", "difficulty", "weak_foot", "is_fun", "is_juggling",
        "is_combination", "is_active",
    )
    search_fields = ("name", "instructions", "cue")
    prepopulated_fields = {"slug": ("name",)}


class PlanDrillInline(admin.TabularInline):
    model = PlanDrill
    extra = 1
    autocomplete_fields = ("drill",)


@admin.register(PlanDay)
class PlanDayAdmin(admin.ModelAdmin):
    list_display = ("plan", "get_weekday_display", "label", "is_rest", "is_optional")
    list_filter = ("plan", "is_rest", "is_optional")
    inlines = [PlanDrillInline]


class PlanDayInline(admin.TabularInline):
    model = PlanDay
    extra = 0


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    inlines = [PlanDayInline]


@admin.register(SessionLog)
class SessionLogAdmin(admin.ModelAdmin):
    list_display = ("date", "drill", "athlete", "completed", "rating")
    list_filter = ("completed", "rating", "date")
    date_hierarchy = "date"


@admin.register(Badge)
class BadgeAdmin(NoDeleteMixin, admin.ModelAdmin):
    """Retire a badge with RETIRED_BADGES in seed_drills.py, never delete it.

    EarnedBadge.badge is CASCADE: deleting a badge here takes his award of
    it with it. A retired badge he earned stays on his record as a Legend.
    """

    list_display = ("name", "emoji", "kind", "threshold", "is_active")
    list_filter = ("kind", "is_active")


@admin.register(EarnedBadge)
class EarnedBadgeAdmin(NoDeleteMixin, admin.ModelAdmin):
    """Already earned stays earned. The one way a badge goes is
    clear_trial_plays, for Dad's trial before the deck is handed over."""

    list_display = ("badge", "athlete", "earned_on")


@admin.register(Card)
class CardAdmin(NoDeleteMixin, admin.ModelAdmin):
    """Retire a card in deck_data.py rather than deleting it here."""

    list_display = ("name", "pack", "scoring", "per_foot", "move", "level", "is_active")
    list_filter = ("pack", "scoring", "per_foot", "is_active")
    search_fields = ("name", "instructions", "cue")


@admin.register(Play)
class PlayAdmin(NoDeleteMixin, admin.ModelAdmin):
    """His scores. Read them here; nothing about a play is typed in.

    The scores are read-only too: the phone keeps its own copy and never
    takes the server's over it, so a score corrected here would still show
    the old number in his bests, and the two copies would quietly disagree.
    """

    list_display = ("date", "card", "weak_score", "score", "athlete", "played_at")
    list_filter = ("card__pack", "date")
    date_hierarchy = "date"
    readonly_fields = (
        "id", "athlete", "card", "date", "played_at", "score", "weak_score",
        # The stamp is written once, on the phone: an edit here would never
        # reach the phone, and would be what a restored phone and 2b's
        # badges read.
        "points", "medal", "bests",
        "created_at",
    )

    def has_add_permission(self, request):
        # A play is made on the phone, id and all; an empty add form only 500s.
        return False
