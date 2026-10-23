from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = "Create a confirmed TOTP device for a user and print its provisioning URI (shown once)."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        user = get_user_model().objects.get(username=username)
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        self.stdout.write(device.config_url)
