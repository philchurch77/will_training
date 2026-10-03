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

Back the disk up first (CLAUDE.md, Deployment). And clear the site's data on
every phone the deck was tried on - in the home-screen app if it was played
there, which on an iPhone keeps its storage apart from Safari's. The phone
keeps its own copy of every play, and when it sees the server no longer has
one it sends it again. Do that with signal, after Today's ticks have gone
through, because it clears Today's offline queue too.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from training.models import Play

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
        if not count:
            return
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
        with transaction.atomic():
            plays.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Cleared {count} plays. Now clear the site data on every phone the deck was tried on."
        ))
