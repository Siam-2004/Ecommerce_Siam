from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from store.models import Category, Product, Order, OrderItem, Wishlist, Coupon, Review, FlashSale
from store.cart import Cart
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Avg, Q
import requests
import google.generativeai as genai
import json
import re
from django.utils import timezone
from .models import StoreSetting

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from io import BytesIO

User = get_user_model()


def send_telegram_message(order_id, total_amount, customer_name):
    bot_token = '8508486732:AAEzI6CrIpxrK4cGfSA-r3Wo8UMYx5H3w_0'
    chat_id = '8344468129'

    message = f"🎉 <b>New Order Received!</b>\n\n" \
              f"👤 <b>Customer:</b> {customer_name}\n" \
              f"🛒 <b>Order ID:</b> #{order_id}\n" \
              f"💰 <b>Total Amount:</b> ৳{total_amount}\n\n" \
              f"🚀 Please check the admin panel to process the order."

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }

    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")


def send_order_email_with_pdf(order, request):
    if not order.email:
        return

    order_items = OrderItem.objects.filter(order=order)

    context = {
        'order': order,
        'order_items': order_items,
        'subtotal': order.subtotal,
        'request': request,
    }

    html = render_to_string('store/invoice_pdf.html', context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)

    if not pdf.err:
        subject = f"Order Confirmation - Invoice #{order.id}"

        # ওয়েবসাইটের মূল লিংক (ডোমেইন) জেনারেট করে ট্র্যাক পেইজের লিংক বানানো হচ্ছে
        domain = request.build_absolute_uri('/')[:-1]
        track_url = f"{domain}{reverse('track_order')}"

        # === NEW: সুন্দর HTML মেইল টেমপ্লেট উইথ 'Track Order' বাটন ===
        html_message = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #f8fafc;">
            <h2 style="color: #22c55e; text-align: center;">অর্ডার কনফার্মড! 🎉</h2>
            <p style="color: #333; font-size: 16px;">Hello <strong>{order.full_name}</strong>,</p>
            <p style="color: #475569; font-size: 15px; line-height: 1.6;">Thank you for shopping with us! Your order <strong>#{order.id}</strong> has been successfully placed. Your total amount is <strong>৳{order.total_price}</strong>.</p>
            <p style="color: #475569; font-size: 15px;">We have attached your detailed PDF invoice with this email.</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{track_url}" style="background-color: #3b82f6; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);">
                    📦 Track Your Order
                </a>
            </div>

            <hr style="border: none; border-top: 1px solid #cbd5e1; margin: 20px 0;">
            <p style="color: #64748b; font-size: 13px; text-align: center;">If you have any questions, feel free to reply to this email.</p>
            <p style="color: #64748b; font-size: 14px; text-align: center;">Regards,<br><strong style="color: #333;">Premium Store Team</strong></p>
        </div>
        """

        email = EmailMessage(
            subject,
            html_message,
            settings.DEFAULT_FROM_EMAIL,
            [order.email]
        )

        # মেইলটাকে প্লেইন টেক্সট থেকে HTML-এ কনভার্ট করার ম্যাজিক!
        email.content_subtype = "html"
        email.attach(f'Invoice_Order_{order.id}.pdf', result.getvalue(), 'application/pdf')

        try:
            email.send()
        except Exception as e:
            print(f"Email sending error: {e}")


def product_list(request, category_slug=None):
    category = None
    categories = Category.objects.all()
    products = Product.objects.filter(is_available=True)

    flash_sale = FlashSale.objects.filter(is_active=True, end_time__gt=timezone.now()).first()

    if request.GET.get('flash_sale') == 'true':
        if flash_sale:
            products = flash_sale.products.filter(is_available=True)
        else:
            products = Product.objects.none()
    else:
        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)
            products = products.filter(category=category)

        min_price = request.GET.get('min_price')
        max_price = request.GET.get('max_price')
        sort_by = request.GET.get('sort')

        if min_price:
            products = products.filter(price__gte=min_price)
        if max_price:
            products = products.filter(price__lte=max_price)

        if sort_by == 'price_asc':
            products = products.order_by('price')
        elif sort_by == 'price_desc':
            products = products.order_by('-price')
        elif sort_by == 'newest':
            products = products.order_by('-id')

    wishlist_product_ids = []
    if request.user.is_authenticated:
        wishlist_product_ids = Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)

    cart = Cart(request)

    context = {
        'category': category,
        'categories': categories,
        'products': products,
        'wishlist_product_ids': wishlist_product_ids,
        'cart': cart,
        'cart_count': len(cart),
        'flash_sale': flash_sale,
    }

    return render(request, 'store/product_list.html', context)


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_available=True)

    related_products = Product.objects.filter(
        category=product.category,
        is_available=True
    ).exclude(id=product.id).order_by('-created_at')[:4]

    reviews = Review.objects.filter(product=product).order_by('-created_at')
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    average_rating = round(average_rating, 1) if average_rating else 0

    total_reviews = reviews.count()
    rating_breakdown = {
        5: reviews.filter(rating=5).count(),
        4: reviews.filter(rating=4).count(),
        3: reviews.filter(rating=3).count(),
        2: reviews.filter(rating=2).count(),
        1: reviews.filter(rating=1).count(),
    }
    rating_percentages = {}
    for star, count in rating_breakdown.items():
        rating_percentages[star] = int((count / total_reviews) * 100) if total_reviews > 0 else 0

    can_review = False
    has_reviewed = False
    is_in_wishlist = False

    if request.user.is_authenticated:
        has_reviewed = Review.objects.filter(product=product, user=request.user).exists()
        is_in_wishlist = Wishlist.objects.filter(user=request.user, product=product).exists()

        if not has_reviewed:
            can_review = OrderItem.objects.filter(
                order__user=request.user,
                order__status='Delivered',
                product=product
            ).exists()

    # Gallery images
    gallery_images = product.images.all()

    # Frequently bought together & bundle calculations
    bundle_items = list(product.frequently_bought_together.filter(is_available=True))
    bundle_total_regular = float(product.price)
    bundle_total_actual = float(product.discount_price if product.discount_price and product.discount_price > 0 else product.price)
    for bi in bundle_items:
        bundle_total_regular += float(bi.price)
        bundle_total_actual += float(bi.discount_price if bi.discount_price and bi.discount_price > 0 else bi.price)

    bundle_discount_percent = product.bundle_discount or 0
    bundle_savings = (bundle_total_actual * bundle_discount_percent) / 100 if bundle_discount_percent > 0 else 0
    bundle_final_price = round(bundle_total_actual - bundle_savings, 2)

    cart = Cart(request)

    context = {
        'product': product,
        'related_products': related_products,
        'reviews': reviews,
        'total_reviews': total_reviews,
        'average_rating': average_rating,
        'rating_breakdown': rating_breakdown,
        'rating_percentages': rating_percentages,
        'can_review': can_review,
        'has_reviewed': has_reviewed,
        'is_in_wishlist': is_in_wishlist,
        'gallery_images': gallery_images,
        'bundle_items': bundle_items,
        'bundle_total_regular': round(bundle_total_regular, 2),
        'bundle_total_actual': round(bundle_total_actual, 2),
        'bundle_savings': round(bundle_savings, 2),
        'bundle_final_price': bundle_final_price,
        'bundle_discount_percent': bundle_discount_percent,
        'cart': cart,
        'cart_count': len(cart)
    }
    return render(request, 'store/product_detail.html', context)


def cart_add_bundle(request, product_id):
    if not request.user.is_authenticated:
        login_url = f"{reverse('login')}?next={request.META.get('HTTP_REFERER', reverse('product_list'))}"
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'login_required',
                'login_url': login_url,
                'message': 'কার্টে বান্ডেল যোগ করতে অনুগ্রহ করে লগইন বা সাইন আপ করুন।'
            }, status=401)
        messages.info(request, "কার্টে বান্ডেল যোগ করতে অনুগ্রহ করে লগইন বা সাইন আপ করুন।")
        return redirect(login_url)

    cart = Cart(request)
    main_product = get_object_or_404(Product, id=product_id)
    size = request.POST.get('size', '')
    cart.add(product=main_product, quantity=1, size=size, override_quantity=False)

    bundle_items = main_product.frequently_bought_together.filter(is_available=True)
    for item in bundle_items:
        cart.add(product=item, quantity=1, size='', override_quantity=False)

    messages.success(request, f"'{main_product.name}' এবং বান্ডেলের আইটেমগুলো কার্টে যোগ করা হয়েছে!")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    return redirect('cart_summary')


@login_required(login_url='login')
def cart_summary(request):
    cart = Cart(request)

    # === BUG FIX: কার্ট খালি থাকলে সেশন রিমুভ ===
    if len(cart) == 0:
        request.session.pop('coupon_code', None)
        request.session.pop('discount_percentage', None)
        request.session.pop('bundle_discount_amount', None)

    return render(request, 'store/cart_summary.html', {'cart': cart})


def cart_add(request, product_id):
    if not request.user.is_authenticated:
        login_url = f"{reverse('login')}?next={request.META.get('HTTP_REFERER', reverse('product_list'))}"
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'login_required',
                'login_url': login_url,
                'message': 'কার্টে প্রোডাক্ট যোগ করতে অনুগ্রহ করে লগইন বা সাইন আপ করুন।'
            }, status=401)
        messages.info(request, "কার্টে প্রোডাক্ট যোগ করতে অনুগ্রহ করে লগইন বা সাইন আপ করুন।")
        return redirect(login_url)

    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)

    # === BUG FIX: নতুন প্রোডাক্ট কার্টে অ্যাড করলে আগের কুপন অটোমেটিক রিমুভ হয়ে যাবে ===
    # এতে করে কাস্টমারকে ম্যানুয়ালি আবার কুপন দিতে হবে, কুপন আর স্টাক হয়ে থাকবে না।
    request.session.pop('coupon_code', None)
    request.session.pop('discount_percentage', None)
    request.session.pop('bundle_discount_amount', None)
    # =========================================================================

    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        size = request.POST.get('size', '')
        cart.add(product=product, quantity=quantity, size=size, override_quantity=False)
    else:
        size = request.GET.get('size', '')
        cart.add(product=product, quantity=1, size=size, override_quantity=False)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    referer = request.META.get('HTTP_REFERER', '')
    if not referer or 'login' in referer or 'register' in referer:
        return redirect('product_list')
    base_url = referer.split('?')[0]
    return redirect(base_url)


@login_required(login_url='login')
def cart_decrement(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    size = request.GET.get('size', '')
    item_id = f"{product.id}_{size}" if size else str(product.id)

    if item_id in cart.cart:
        current_qty = cart.cart[item_id]['quantity']
        if current_qty > 1:
            cart.add(product=product, quantity=current_qty - 1, size=size, override_quantity=True)

    # === BUG FIX: কার্ট খালি হলে কুপন মুছে যাবে ===
    if len(cart) == 0:
        request.session.pop('coupon_code', None)
        request.session.pop('discount_percentage', None)
        request.session.pop('bundle_discount_amount', None)
    else:
        request.session.pop('bundle_discount_amount', None)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    referer = request.META.get('HTTP_REFERER', 'product_list')
    return redirect(referer)


@login_required(login_url='login')
def cart_remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    size = request.GET.get('size', '')
    cart.remove(product, size)

    # === BUG FIX: কার্ট খালি হলে কুপন মুছে যাবে ===
    if len(cart) == 0:
        request.session.pop('coupon_code', None)
        request.session.pop('discount_percentage', None)
        request.session.pop('bundle_discount_amount', None)
    else:
        request.session.pop('bundle_discount_amount', None)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    referer = request.META.get('HTTP_REFERER', 'product_list')
    return redirect(referer)


@login_required(login_url='login')
def checkout(request):
    cart = Cart(request)

    if len(cart) == 0:
        request.session.pop('coupon_code', None)
        request.session.pop('discount_percentage', None)
        request.session.pop('bundle_discount_amount', None)
        return redirect('product_list')

    subtotal = float(cart.get_total_price())

    cart_product_ids = []
    for key in cart.cart.keys():
        try:
            cart_product_ids.append(int(str(key).split('_')[0]))
        except ValueError:
            pass

    bundle_discount_amount = 0.0
    for p_id in cart_product_ids:
        try:
            p = Product.objects.get(id=p_id)
            if getattr(p, 'bundle_discount', 0) > 0:
                fb_ids = list(p.frequently_bought_together.values_list('id', flat=True))
                intersect = set(fb_ids).intersection(set(cart_product_ids))
                if intersect:
                    bundle_total = float(p.discount_price or p.price)
                    for i_id in intersect:
                        fb_p = Product.objects.get(id=i_id)
                        bundle_total += float(fb_p.discount_price or fb_p.price)
                    bundle_discount_amount += (bundle_total * p.bundle_discount) / 100
        except Product.DoesNotExist:
            continue

    if bundle_discount_amount > 0:
        total_discount_amount = bundle_discount_amount
        coupon_percentage = 0
        coupon_code = ''
        request.session['bundle_discount_amount'] = bundle_discount_amount
        request.session.pop('coupon_code', None)
        request.session.pop('discount_percentage', None)
    else:
        request.session.pop('bundle_discount_amount', None)
        coupon_code = request.session.get('coupon_code', '')
        coupon_percentage = request.session.get('discount_percentage', 0)
        total_discount_amount = (subtotal * coupon_percentage) / 100

    # ==============================================================
    # === Fetch Free Shipping Status & Threshold from StoreSetting ==
    # ==============================================================
    store_setting = StoreSetting.objects.first()
    is_free_shipping = store_setting.is_free_shipping_active if store_setting else True
    free_shipping_threshold = float(store_setting.free_shipping_threshold) if store_setting else 3000.00
    # ==============================================================

    final_subtotal = max(0.0, subtotal - total_discount_amount)
    initial_shipping = 0.0 if (is_free_shipping and final_subtotal >= free_shipping_threshold) else 60.0
    grand_total = final_subtotal + initial_shipping

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        payment_method = request.POST.get('payment_method')
        sender_number = request.POST.get('sender_number')
        trx_id = request.POST.get('trx_id')

        # === UPDATE: Check if subtotal is greater than threshold to make shipping FREE ===
        raw_shipping_charge = float(request.POST.get('shipping_area', 60))
        final_subtotal = subtotal - total_discount_amount

        # Apply Zero Shipping logic at backend safely if offer is active
        if is_free_shipping and final_subtotal >= free_shipping_threshold:
            shipping_charge = 0.0
        else:
            shipping_charge = raw_shipping_charge

        total_price = final_subtotal + shipping_charge
        # ===============================================================================

        order = Order.objects.create(
            user=request.user,
            full_name=full_name,
            email=email,
            phone=phone,
            address=address,
            payment_method=payment_method,
            sender_number=sender_number,
            trx_id=trx_id,
            subtotal=subtotal,
            discount_amount=total_discount_amount,
            shipping_charge=shipping_charge,
            total_price=total_price,
            status='Pending'
        )

        for item in cart:
            product = item['product']
            quantity = item['quantity']
            price = item['price']
            size = item.get('size', '')

            OrderItem.objects.create(
                order=order,
                product=product,
                price=price,
                quantity=quantity,
                size=size
            )

        # === MARK ABANDONED CART AS RECOVERED ===
        try:
            from store.models import AbandonedCart
            from django.utils import timezone
            from django.db.models import Q
            AbandonedCart.objects.filter(
                Q(user=request.user) | (Q(email__isnull=False) & Q(email__iexact=email)),
                is_recovered=False
            ).update(is_recovered=True, recovered_at=timezone.now())
        except Exception as e:
            print(f"Error marking abandoned cart as recovered: {e}")

        cart.clear()

        request.session.pop('coupon_code', None)
        request.session.pop('discount_percentage', None)
        request.session.pop('bundle_discount_amount', None)

        send_telegram_message(order_id=order.id, total_amount=order.total_price, customer_name=order.full_name)
        send_order_email_with_pdf(order, request)

        return render(request, 'store/order_success.html', {'order': order})

    context = {
        'cart': cart,
        'subtotal': subtotal,
        'final_subtotal': final_subtotal,
        'coupon_code': coupon_code,
        'discount_percentage': coupon_percentage,
        'discount_amount': total_discount_amount,
        'shipping_charge': initial_shipping,
        'grand_total': grand_total,
        'is_free_shipping_active': is_free_shipping,
        'free_shipping_threshold': free_shipping_threshold,
    }
    return render(request, 'store/checkout.html', context)


def track_order(request):
    order = None
    error = None
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        phone = request.POST.get('phone')

        try:
            order = Order.objects.get(id=order_id, phone=phone)
        except Order.DoesNotExist:
            error = "Order missing or Phone number does not match!"

    return render(request, 'store/track_order.html', {'order': order, 'error': error})


def user_register(request):
    next_url = request.POST.get('next') or request.GET.get('next')

    if request.user.is_authenticated:
        if next_url and next_url.startswith('/') and not next_url.startswith('//'):
            return redirect(next_url)
        return redirect('product_list')

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        login_url = reverse('login')
        if next_url:
            login_url += f'?next={next_url}'

        if password != confirm_password:
            messages.error(request, "পাসওয়ার্ড দুটি মিলছে না!")
            return redirect(login_url)

        if User.objects.filter(email=email).exists():
            messages.error(request, "এই ইমেইল দিয়ে ইতিমধ্যে একাউন্ট তৈরি করা আছে!")
            return redirect(login_url)

        user = User.objects.create_user(email=email, password=password)
        user.first_name = full_name
        user.save()

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, f"স্বাগতম {user.first_name or user.email}! সফলভাবে অ্যাকাউন্ট তৈরি হয়েছে।")

        if next_url and next_url.startswith('/') and not next_url.startswith('//'):
            return redirect(next_url)
        return redirect('product_list')

    return render(request, 'store/auth.html', {'next': next_url})


def user_login(request):
    next_url = request.POST.get('next') or request.GET.get('next')

    if request.user.is_authenticated:
        if next_url and next_url.startswith('/') and not next_url.startswith('//'):
            return redirect(next_url)
        return redirect('product_list')

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        if not email:
            email = request.POST.get('username')

        user = authenticate(request, email=email, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"স্বাগতম {user.first_name or user.email}! সফলভাবে লগইন হয়েছে।")
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect('product_list')
        else:
            messages.error(request, "ইমেইল বা পাসওয়ার্ড ভুল হয়েছে!")
            login_url = reverse('login')
            if next_url:
                login_url += f'?next={next_url}'
            return redirect(login_url)

    return render(request, 'store/auth.html', {'next': next_url})


def user_logout(request):
    logout(request)
    messages.info(request, "সফলভাবে লগআউট করা হয়েছে।")
    return redirect('product_list')


@login_required(login_url='login')
def user_profile(request):
    cart = Cart(request)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    flash_sale = FlashSale.objects.filter(is_active=True, end_time__gt=timezone.now()).first()

    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        email = request.POST.get('email')

        if User.objects.filter(email=email).exclude(id=request.user.id).exists():
            messages.error(request, 'এই ইমেইলটি অন্য একটি অ্যাকাউন্টে ব্যবহৃত হচ্ছে! অন্য ইমেইল দিন।')
        else:
            user = request.user
            user.first_name = first_name
            user.email = email
            user.save()

            messages.success(request, 'আপনার প্রোফাইলের তথ্য সফলভাবে আপডেট করা হয়েছে!')
            return redirect('profile')

    context = {
        'orders': orders,
        'flash_sale': flash_sale,
        'cart_count': len(cart),
    }
    return render(request, 'store/profile.html', context)


@login_required(login_url='login')
def user_address(request):
    last_order = Order.objects.filter(user=request.user).order_by('-created_at').first()
    context = {
        'address': last_order.address if last_order else None,
        'phone': last_order.phone if last_order else None
    }
    return render(request, 'store/address.html', context)


@login_required(login_url='login')
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'store/order_history.html', {'orders': orders})


GEMINI_API_KEY = "AQ.Ab8RN6Jew8UhFbPRAjZeH3Z5NSePmR_iercrN10YNq7qXUuCEQ"


def search_products(request):
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({'data': []})

    words = query.split()
    lower_query = query.lower()

    ai_trigger_keywords = [
        'taka', 'takar', 'টাকা', 'টাকার', 'under', 'below', 'moddhe', 'মধ্যে', 'কম',
        'budget', 'over', 'above', 'beshi', 'বেশি', 'উপরে', 'দাম'
    ]
    has_number = any(char.isdigit() for char in query)
    has_ai_trigger = any(kw in lower_query for kw in ai_trigger_keywords)

    needs_ai = has_ai_trigger or (has_number and len(words) > 1)

    if not needs_ai:
        products = Product.objects.filter(name__icontains=query, is_available=True)[:6]
        if not products.exists() and len(words) > 1:
            kw_filter = Q()
            for w in words:
                if len(w) > 1:
                    kw_filter |= Q(name__icontains=w) | Q(category__name__icontains=w)
            products = Product.objects.filter(kw_filter, is_available=True)[:6]

        results = [{
            'name': p.name,
            'price': str(p.discount_price if p.discount_price and p.discount_price > 0 else p.price),
            'image': p.image.url if p.image else '',
            'url': reverse('product_detail', args=[p.slug])
        } for p in products]
        return JsonResponse({'data': results})

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            generation_config={"response_mime_type": "application/json"}
        )

        prompt = f"""
        Analyze user shopping query: "{query}"
        Extract search keywords and price filters in JSON format ONLY:
        {{
            "keywords": ["list", "of", "product", "names", "only"],
            "min_price": null or integer (Use this if query implies 'over', 'above', 'beshi', 'উপরে', 'বেশি', 'more than'),
            "max_price": null or integer (Use this if query implies 'under', 'below', 'moddhe', 'কম', 'মধ্যে', 'less than')
        }}
        Note: Do not include words like 'under', 'over', 'taka', 'beshi' in keywords.
        """

        response = model.generate_content(prompt, request_options={"timeout": 4})
        search_params = json.loads(response.text.strip())

        products = Product.objects.filter(is_available=True)

        if search_params.get('max_price'):
            products = products.filter(price__lte=search_params['max_price'])
        if search_params.get('min_price'):
            products = products.filter(price__gte=search_params['min_price'])

        keywords = search_params.get('keywords', [])
        if keywords:
            kw_filter = Q()
            for kw in keywords:
                if len(kw) > 1 and not kw.isdigit():
                    kw_filter |= Q(name__icontains=kw) | Q(category__name__icontains=kw)
            matched = products.filter(kw_filter)
            if matched.exists():
                products = matched

        products = products[:6]
        results = [{
            'name': p.name,
            'price': str(p.discount_price if p.discount_price and p.discount_price > 0 else p.price),
            'image': p.image.url if p.image else '',
            'url': reverse('product_detail', args=[p.slug])
        } for p in products]

        return JsonResponse({'data': results})

    except Exception as e:
        print(f"AI Search Fallback: {e}")
        products = Product.objects.filter(is_available=True)
        text_words = [w for w in words if not w.isdigit() and w.lower() not in ai_trigger_keywords]

        if text_words:
            kw_filter = Q()
            for w in text_words:
                if len(w) > 1:
                    kw_filter |= Q(name__icontains=w) | Q(category__name__icontains=w)
            matched = products.filter(kw_filter)
            if matched.exists():
                products = matched

        numbers = re.findall(r'\d+', query)
        if numbers:
            price_limit = int(numbers[0])
            over_keywords = ['over', 'above', 'beshi', 'upore', 'বেশি', 'উপরে', '>']
            if any(kw in lower_query for kw in over_keywords):
                products = products.filter(price__gte=price_limit)
            else:
                products = products.filter(price__lte=price_limit)
        elif not text_words:
            products = products.filter(name__icontains=query)

        products = products[:6]
        results = [{
            'name': p.name,
            'price': str(p.discount_price if p.discount_price and p.discount_price > 0 else p.price),
            'image': p.image.url if p.image else '',
            'url': reverse('product_detail', args=[p.slug])
        } for p in products]

        return JsonResponse({'data': results})


@login_required(login_url='login')
def toggle_wishlist(request, product_id):
    product = Product.objects.get(id=product_id)
    wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, product=product)

    if not created:
        wishlist_item.delete()
        return JsonResponse({'status': 'removed'})
    else:
        return JsonResponse({'status': 'added'})


@login_required(login_url='login')
def wishlist_view(request):
    wishlist_items = Wishlist.objects.filter(user=request.user).order_by('-added_at')
    cart = Cart(request)

    context = {
        'wishlist_items': wishlist_items,
        'cart': cart,
        'cart_count': len(cart),
    }

    return render(request, 'store/wishlist.html', context)


def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    response = HttpResponse(content_type='application/pdf')

    response['Content-Disposition'] = 'inline; filename="invoice.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response


@login_required(login_url='login')
def generate_invoice(request, order_id):
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order, id=order_id)
    else:
        from django.db.models import Q
        order = get_object_or_404(Order, Q(user=request.user) | (Q(email__isnull=False) & Q(email__iexact=request.user.email)), id=order_id)
    order_items = OrderItem.objects.filter(order=order)

    context = {
        'order': order,
        'order_items': order_items,
        'subtotal': order.subtotal,
        'request': request,
    }
    return render_to_pdf('store/invoice_pdf.html', context)


def apply_coupon(request):
    cart = Cart(request)

    if len(cart) == 0:
        messages.error(request, "আপনার কার্ট খালি! কুপন ব্যবহার করতে আগে প্রোডাক্ট যুক্ত করুন।")
        return redirect(request.META.get('HTTP_REFERER', 'product_list'))

    cart_product_ids = []
    for key in cart.cart.keys():
        try:
            cart_product_ids.append(int(str(key).split('_')[0]))
        except ValueError:
            pass

    is_bundle_active = False
    for p_id in cart_product_ids:
        try:
            p = Product.objects.get(id=p_id)
            if getattr(p, 'bundle_discount', 0) > 0:
                fb_ids = list(p.frequently_bought_together.values_list('id', flat=True))
                if set(fb_ids).intersection(set(cart_product_ids)):
                    is_bundle_active = True
                    break
        except Product.DoesNotExist:
            continue

    if is_bundle_active:
        messages.error(request, "দুঃখিত, বান্ডেল অফারের সাথে অন্য কোনো কুপন ব্যবহার করা যাবে না!")
        return redirect(request.META.get('HTTP_REFERER', 'checkout'))

    if request.method == 'POST':
        code = request.POST.get('coupon_code', '').strip()
        try:
            coupon = Coupon.objects.get(code__iexact=code, is_active=True)
            request.session['coupon_code'] = coupon.code
            request.session['discount_percentage'] = coupon.discount_percentage
            messages.success(request,
                             f"কুপন '{coupon.code}' সফলভাবে অ্যাপ্লাই হয়েছে! ({coupon.discount_percentage}% ডিসকাউন্ট)")
        except Coupon.DoesNotExist:
            request.session.pop('coupon_code', None)
            request.session.pop('discount_percentage', None)
            messages.error(request, "দুঃখিত, কুপনটি ইনভ্যালিড বা মেয়াদোত্তীর্ণ!")

    return redirect(request.META.get('HTTP_REFERER', 'checkout'))


@login_required(login_url='login')
def submit_review(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')

        # === NEW: কাস্টমারের আপলোড করা ছবি রিসিভ করার কোড ===
        review_image = request.FILES.get('review_image')

        if Review.objects.filter(product=product, user=request.user).exists():
            messages.error(request, "আপনি ইতিমধ্যে এই প্রোডাক্টের রিভিউ দিয়েছেন!")
            return redirect('product_detail', slug=product.slug)

        Review.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            comment=comment,
            image=review_image  # === NEW: ডাটাবেজে ছবি সেভ হচ্ছে ===
        )
        messages.success(request, "আপনার রিভিউ সফলভাবে যুক্ত হয়েছে! মতামতের জন্য ধন্যবাদ।")
        return redirect('product_detail', slug=product.slug)

    return redirect('product_list')