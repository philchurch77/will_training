"""How a score and a medal read on the coach page - the same as on the phone
(scoreText and medalText in deck.js)."""

from django import template

from training.models import Card, Play

register = template.Library()

MEDAL_WORDS = dict(Play.MEDAL_CHOICES)


@register.filter
def score(value, scoring):
    """A time card's score is tenths of a second; anything else is a count."""
    if value is None:
        return "—"
    if scoring == Card.TIME:
        # A 0 on a time card is no time at all: never a best, never "0.0 s".
        return f"{value / 10:.1f} s" if value else "—"
    return str(value)


@register.filter
def medal(value):
    """A word and stars, never a colour on its own. Nothing for no medal."""
    if not value:
        return ""
    word = MEDAL_WORDS.get(value)
    return f"{word} {'★' * value}" if word else ""
