"""Forms for the coach screens.

Will never sees a form other than the PIN pad, so these are plain and
functional rather than designed.
"""

from django import forms

from .models import Drill, PlanDay


class DrillForm(forms.ModelForm):
    class Meta:
        model = Drill
        fields = [
            "name",
            "slug",
            "skill",
            "instructions",
            "cue",
            "duration_minutes",
            "target_reps",
            "needs_ball",
            "needs_wall",
            "needs_cones",
            "needs_space",
            "difficulty",
            "weak_foot",
            "is_fun",
            "is_active",
        ]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "instructions": (
                "Two or three short sentences, written for Will to read himself. "
                "Plain language, no jargon."
            ),
        }

    def clean(self):
        cleaned = super().clean()
        minutes = cleaned.get("duration_minutes")
        reps = cleaned.get("target_reps")
        if (minutes is None) == (reps is None):
            raise forms.ValidationError(
                "Give this drill either a duration in minutes or a target "
                "number of reps - one or the other, not both."
            )
        return cleaned


class PlanDayForm(forms.ModelForm):
    class Meta:
        model = PlanDay
        fields = ["label", "target_minutes", "is_rest", "is_optional"]
