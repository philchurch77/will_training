"""Clear the plays Dad made trying the deck, before it is handed to Will.

There is one profile, so every card played while trying /deck/ out goes on
Will's record. This is the one deliberate way to take them off again. It is
the only code anywhere that deletes a Play: the admin cannot (NoDeleteMixin),
and Play.card and Play.athlete are PROTECT.

Three things stand between it and his real record:

* --through DATE is required, and only plays dated on or before it go. Pick
  the last day of the trial and anything he plays afterwards is untouched.
* It deletes nothing without --confirm, and --confirm needs --expect N, the
  count the dry run printed. If the number has moved since you read it -
  he has played a card in the meantime - it refuses.
* It goes in leg 3 of docs/chart/deck.md: once the deck is on his tab bar,
  every play is his, and this command must be removed.

The deck's badges go with the plays: every active deck-kind EarnedBadge is
deleted and then awarded again from the plays that are left, in the same
transaction. A retired (Legend) deck badge is kept - it would never be
awarded again. Deleting only the ones dated before --through would keep a
badge that later plays earned only with the trial plays' help. The re-awards
carry today's date, which costs nothing before hand-over. The old app's
badges are never touched.

Back the disk up first (CLAUDE.md, Deployment). And clear the site's data on
every phone the deck was tried on - in the home-screen app if it was played
there, which on an iPhone keeps its storage apart from Safari's. The phone
keeps its own copy of every play, and when it sees the server no longer has
one it sends it again. Do that with signal, after Today's ticks have gone
through, because it clears Today's offline queue too.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from training.deck_rules import award_deck_badges
from training.models import Badge, EarnedBadge, Play

BACKUP = (
    "python -c \"import sqlite3,datetime; s=sqlite3.connect('/var/data/db.sqlite3'); "
    "d=sqlite3.connect('/var/data/db-backup-%s.sqlite3'%datetime.date.today().isoformat()); "
    's.backup(d); d.close(); s.close()"'
)


class Command(BaseCommand):
    help = "Delete deck plays dated on or before --through. Trial plays only, before hand-over."

    def add_arguments(self, parser):
        parser.add_argument(
            "--through", required=True, type=date.fromisoformat,
            help="Last day of the trial, YYYY-MM-DD. Later plays are kept.",
        )
        parser.add_argument(
            "--expect", type=int,
            help="The count the dry run printed. Required with --confirm.",
        )
        parser.add_argument(
            "--confirm", action="store_true",
            help="Actually delete. Without it, only counts.",
        )

    def handle(self, *args, through, expect, confirm, **options):
        plays = Play.objects.filter(date__lte=through)
        count = plays.count()
        kept = Play.objects.filter(date__gt=through).count()
        self.stdout.write(
            f"{count} plays dated on or before {through}; "
            f"{kept} later {'one is' if kept == 1 else 'ones are'} kept."
        )
        for row in plays.values("athlete__username").annotate(n=Count("pk")).order_by("athlete__username"):
            self.stdout.write(f"  {row['athlete__username']}: {row['n']}")
        # Retired (Legend) deck badges are kept: they would never be awarded again.
        deck_badges = EarnedBadge.objects.filter(
            badge__kind__in=Badge.DECK_KINDS, badge__is_active=True
        )
        if not count:
            return
        n = deck_badges.count()
        if n:
            self.stdout.write(
                f"{n} deck {'badge' if n == 1 else 'badges'} would be cleared and "
                "awarded again from the plays left."
            )
        if not confirm:
            self.stdout.write(
                "Nothing deleted. Back the disk up first:\n"
                f"  {BACKUP}\n"
                f"then run again with --confirm --expect {count}, and clear the site data on\n"
                "every phone the deck was tried on, or it sends the plays back."
            )
            return
        if expect is None:
            raise CommandError(
                f"--confirm needs --expect {count}, the count above. Nothing deleted."
            )
        if expect != count:
            raise CommandError(
                f"--expect {expect} does not match the {count} plays found. "
                "Nothing deleted. Run without --confirm and read the count again."
            )
        today = timezone.localdate()
        with transaction.atomic():
            plays.delete()
            deck_badges.delete()
            again = 0
            for athlete in get_user_model().objects.filter(plays__isnull=False).distinct():
                again += len(award_deck_badges(athlete, today))
        self.stdout.write(self.style.SUCCESS(
            f"Cleared {count} plays; {again} deck badges awarded again from the plays left. "
            "Now clear the site data on every phone the deck was tried on."
        ))
