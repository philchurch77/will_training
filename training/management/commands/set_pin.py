"""Change somebody's 4-digit PIN.

    python manage.py set_pin will 4321
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Set the 4-digit PIN for a profile, e.g. set_pin will 4321"

    def add_arguments(self, parser):
        parser.add_argument("username", help="will or coach")
        parser.add_argument("pin", help="Exactly four digits")

    def handle(self, *args, **options):
        username = options["username"].strip().lower()
        pin = options["pin"].strip()

        if len(pin) != 4 or not pin.isdigit():
            raise CommandError("The PIN must be exactly four digits, e.g. 4321.")

        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            names = ", ".join(User.objects.values_list("username", flat=True))
            raise CommandError(
                f"No profile called '{username}'. Profiles are: {names or 'none yet'}."
            )

        user.set_password(pin)
        user.save()
        self.stdout.write(
            self.style.SUCCESS(f"PIN updated for {user.first_name or user.username}.")
        )
