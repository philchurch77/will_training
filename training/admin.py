from django.contrib import admin

from .models import (
    Badge,
    Drill,
    EarnedBadge,
    PlanDay,
    PlanDrill,
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
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("name", "emoji", "kind", "threshold")
    list_filter = ("kind",)


@admin.register(EarnedBadge)
class EarnedBadgeAdmin(admin.ModelAdmin):
    list_display = ("badge", "athlete", "earned_on")
