import random
import string
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.urls import reverse
from store.models import Product, Coupon, StoreSetting, AbandonedCart


def get_cart_items_details(cart_data, domain=None):
    """
    Parses stored cart_data JSON and retrieves full Product objects and images.
    """
    items = []
    if not isinstance(cart_data, dict):
        return items

    product_ids = [v.get('product_id') for v in cart_data.values() if isinstance(v, dict) and 'product_id' in v]
    products = {str(p.id): p for p in Product.objects.filter(id__in=product_ids)}

    for item_key, item_info in cart_data.items():
        if not isinstance(item_info, dict):
            continue
        p_id = str(item_info.get('product_id'))
        product = products.get(p_id)
        if product:
            qty = int(item_info.get('quantity', 1))
            try:
                price = float(item_info.get('price', product.price))
            except (ValueError, TypeError):
                price = float(product.price)

            image_url = None
            if product.image:
                if domain:
                    image_url = f"{domain.rstrip('/')}{product.image.url}"
                else:
                    image_url = product.image.url

            items.append({
                'product': product,
                'name': product.name,
                'image_url': image_url,
                'size': item_info.get('size', ''),
                'quantity': qty,
                'price': price,
                'total': price * qty,
            })
    return items


def generate_recovery_coupon(discount_percent, cart_id):
    """
    Generates a unique, active coupon for this abandoned cart.
    """
    if discount_percent <= 0:
        return None

    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    code = f"SAVE{discount_percent}-C{cart_id}-{random_suffix}"
    coupon, _ = Coupon.objects.get_or_create(
        code=code,
        defaults={
            'discount_percentage': discount_percent,
            'is_active': True
        }
    )
    return coupon


def send_abandoned_cart_email(abandoned_cart, domain=None, force=False):
    """
    Sends a high-converting, luxury abandoned cart recovery email to the customer.
    """
    try:
        store_setting = StoreSetting.objects.first()
        if not store_setting:
            store_setting = StoreSetting.objects.create()

        # If disabled and not a forced manual send from admin, skip
        if not store_setting.abandoned_cart_active and not force:
            return False, "Abandoned cart recovery is currently inactive in Store Settings."

        recipient_email = abandoned_cart.email or (abandoned_cart.user.email if abandoned_cart.user else None)
        if not recipient_email:
            return False, "No recipient email found for this cart."

        if abandoned_cart.is_recovered and not force:
            return False, "This cart has already been recovered/purchased."

        # Determine domain
        if not domain:
            domain = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')

        # Customer name
        customer_name = "সম্মানিত গ্রাহক"
        if abandoned_cart.user:
            if abandoned_cart.user.first_name:
                customer_name = abandoned_cart.user.first_name
            elif hasattr(abandoned_cart.user, 'full_name') and abandoned_cart.user.full_name:
                customer_name = abandoned_cart.user.full_name

        # Calculate items
        items = get_cart_items_details(abandoned_cart.cart_data, domain=domain)
        if not items:
            return False, "No valid products found in this cart."

        # Coupon generation
        discount_percent = store_setting.abandoned_cart_discount_percent
        coupon = None
        if discount_percent > 0:
            if abandoned_cart.coupon_code:
                coupon = Coupon.objects.filter(code=abandoned_cart.coupon_code, is_active=True).first()
            if not coupon:
                coupon = generate_recovery_coupon(discount_percent, abandoned_cart.id)
                abandoned_cart.coupon_code = coupon.code
                abandoned_cart.discount_percent = discount_percent

        cart_url = f"{domain.rstrip('/')}{reverse('cart_summary')}"
        subject = store_setting.abandoned_cart_email_subject or "আপনার কার্টের পছন্দের পণ্যগুলো আপনার জন্য অপেক্ষা করছে!"

        context = {
            'customer_name': customer_name,
            'items': items,
            'total_price': abandoned_cart.total_price,
            'coupon_code': coupon.code if coupon else None,
            'discount_percent': discount_percent if coupon else 0,
            'cart_url': cart_url,
            'domain': domain,
        }

        html_content = render_to_string('store/emails/abandoned_cart_email.html', context)
        text_content = strip_tags(html_content)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        # Update abandoned cart record
        abandoned_cart.is_email_sent = True
        abandoned_cart.email_sent_at = timezone.now()
        abandoned_cart.save()

        return True, f"Recovery email successfully sent to {recipient_email}."
    except Exception as e:
        return False, str(e)
