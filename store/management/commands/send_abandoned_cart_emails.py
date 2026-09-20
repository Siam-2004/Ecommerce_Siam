import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from store.models import StoreSetting, AbandonedCart
from store.cart_recovery import send_abandoned_cart_email


class Command(BaseCommand):
    help = 'Sends abandoned cart recovery emails with discount coupons to customers who left items in their cart.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sending emails even if abandoned cart recovery is turned off in settings.',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=None,
            help='Override the delay hours threshold configured in Store Settings.',
        )
        parser.add_argument(
            '--domain',
            type=str,
            default=None,
            help='The base domain of the website (e.g., https://mystore.com). Defaults to SITE_URL or localhost.',
        )

    def handle(self, *args, **options):
        force = options['force']
        hours_override = options['hours']
        domain = options['domain'] or getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')

        store_setting = StoreSetting.objects.first()
        if not store_setting:
            store_setting = StoreSetting.objects.create()

        if not store_setting.abandoned_cart_active and not force:
            self.stdout.write(self.style.WARNING(
                'Abandoned cart recovery is disabled in Store Settings. Use --force to run anyway.'
            ))
            return

        delay_hours = hours_override if hours_override is not None else store_setting.abandoned_cart_wait_hours
        cutoff_time = timezone.now() - datetime.timedelta(hours=delay_hours)

        abandoned_carts = AbandonedCart.objects.filter(
            is_recovered=False,
            is_email_sent=False,
            updated_at__lte=cutoff_time
        )

        total_found = abandoned_carts.count()
        self.stdout.write(self.style.NOTICE(
            f"Found {total_found} abandoned cart(s) older than {delay_hours} hour(s) (Cutoff: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')})."
        ))

        sent_count = 0
        failed_count = 0

        for cart in abandoned_carts:
            success, message = send_abandoned_cart_email(cart, domain=domain, force=force)
            if success:
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [SUCCESS] Cart #{cart.id} -> {message}"))
            else:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  [FAILED] Cart #{cart.id} -> {message}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nCompleted! Successfully sent: {sent_count}, Failed/Skipped: {failed_count}."
        ))
