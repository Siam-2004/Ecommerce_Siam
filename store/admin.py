from django.contrib import admin
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db import models
from django.forms import CheckboxSelectMultiple
from django.urls import reverse
from django.conf import settings
from .models import Category, Brand, Size, Product, Order, OrderItem, Coupon, Review, ProductImage, FlashSale, StoreSetting, AbandonedCart


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'price', 'quantity', 'size']


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # === UPDATE: bundle_discount অ্যাড করা হলো ===
    list_display = ['name', 'price', 'discount_price', 'bundle_discount', 'stock', 'category', 'is_available']
    list_filter = ['is_available', 'category', 'brand']

    # === UPDATE: bundle_discount এখন অ্যাডমিন প্যানেল থেকেই চেঞ্জ করা যাবে ===
    list_editable = ['price', 'discount_price', 'bundle_discount', 'stock', 'is_available']
    prepopulated_fields = {'slug': ('name',)}

    formfield_overrides = {
        models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }
    inlines = [ProductImageInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'full_name', 'email', 'phone', 'total_price', 'payment_method', 'trx_id', 'status']
    list_filter = ['status', 'created_at']
    list_editable = ['status']
    inlines = [OrderItemInline]

    def send_status_email(self, request, obj):
        try:
            domain = request.build_absolute_uri('/')[:-1]
            track_url = f"{domain}{reverse('track_order')}"

            subject = f"Order #{obj.id} Update - Premium Store"
            from_email = settings.DEFAULT_FROM_EMAIL
            to = [obj.email]

            if obj.status == 'Delivered':
                title = "প্রোডাক্ট ডেলিভারি সম্পন্ন হয়েছে! 🎉"
                message = f"আপনার অর্ডার <strong>#{obj.id}</strong> সফলভাবে ডেলিভারি করা হয়েছে। আপনার অভিজ্ঞতা আমাদের সাথে শেয়ার করুন!"
                btn_text = "⭐ রিভিউ দিন ও বিস্তারিত দেখুন"
                btn_color = "#22c55e"
            elif obj.status == 'Cancelled':
                title = "অর্ডারটি বাতিল করা হয়েছে ❌"
                message = f"দুঃখিত, কোনো কারণে আপনার অর্ডার <strong>#{obj.id}</strong> বাতিল করা হয়েছে। বিস্তারিত জানতে আমাদের সাথে যোগাযোগ করুন।"
                btn_text = "বিস্তারিত দেখুন"
                btn_color = "#ef4444"
            else:
                title = "অর্ডারের স্ট্যাটাস আপডেট 📦"
                message = f"আপনার অর্ডার <strong>#{obj.id}</strong> এর বর্তমান স্ট্যাটাস: <strong style='color:#3b82f6;'>{obj.status}</strong>"
                btn_text = "🚚 ট্র্যাক অর্ডার"
                btn_color = "#3b82f6"

            html_content = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #f8fafc;">
                <h2 style="color: #1e293b; text-align: center;">{title}</h2>
                <p style="color: #334155; font-size: 16px;">Hello <strong>{obj.full_name}</strong>,</p>
                <p style="color: #475569; font-size: 15px; line-height: 1.6;">{message}</p>

                <div style="text-align: center; margin: 35px 0;">
                    <a href="{track_url}" style="background-color: {btn_color}; color: #ffffff; padding: 14px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);">
                        {btn_text}
                    </a>
                </div>

                <hr style="border: none; border-top: 1px dashed #cbd5e1; margin: 25px 0;">
                <p style="color: #64748b; font-size: 13px; text-align: center;">If you have any questions, feel free to reply to this email.</p>
            </div>
            """

            text_content = strip_tags(html_content)

            if obj.email:
                msg = EmailMultiAlternatives(subject, text_content, from_email, to)
                msg.attach_alternative(html_content, "text/html")
                msg.send()
                print("Custom HTML Email sent successfully!")
        except Exception as e:
            print(f"Failed to send email: {e}")

    def save_model(self, request, obj, form, change):
        if change:
            old_order = Order.objects.get(pk=obj.pk)
            if old_order.status != obj.status:
                self.send_status_email(request, obj)
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, Order):
                try:
                    old_order = Order.objects.get(pk=obj.pk)
                    if old_order.status != obj.status:
                        self.send_status_email(request, obj)
                except Order.DoesNotExist:
                    pass
            obj.save()
        formset.save_m2m()


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percentage', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user__email')


@admin.register(FlashSale)
class FlashSaleAdmin(admin.ModelAdmin):
    list_display = ('title', 'end_time', 'is_active')
    list_editable = ('is_active',)

    formfield_overrides = {
        models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }

@admin.register(StoreSetting)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'is_free_shipping_active',
        'free_shipping_threshold',
        'abandoned_cart_active',
        'abandoned_cart_wait_hours',
        'abandoned_cart_discount_percent'
    )
    list_editable = (
        'is_free_shipping_active',
        'free_shipping_threshold',
        'abandoned_cart_active',
        'abandoned_cart_wait_hours',
        'abandoned_cart_discount_percent'
    )


@admin.register(AbandonedCart)
class AbandonedCartAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_customer',
        'total_price',
        'item_count_display',
        'coupon_code',
        'is_email_sent',
        'email_sent_at',
        'is_recovered',
        'updated_at'
    )
    list_filter = ('is_recovered', 'is_email_sent', 'created_at', 'updated_at')
    search_fields = ('email', 'phone', 'coupon_code', 'user__email')
    readonly_fields = (
        'cart_preview_html',
        'created_at',
        'updated_at',
        'email_sent_at',
        'recovered_at'
    )
    actions = ['send_recovery_email_action', 'mark_as_recovered_action']

    @admin.display(description="কাস্টমার")
    def get_customer(self, obj):
        if obj.user:
            return f"{obj.user.email} (ইউজার)"
        return obj.email or f"Guest #{obj.id}"

    @admin.display(description="আইটেম সংখ্যা")
    def item_count_display(self, obj):
        return f"{obj.item_count} টি"

    @admin.display(description="কার্টের প্রোডাক্টসমূহ")
    def cart_preview_html(self, obj):
        from .cart_recovery import get_cart_items_details
        items = get_cart_items_details(obj.cart_data)
        if not items:
            return "কার্ট খালি"
        html = '<div style="max-width:600px;">'
        for item in items:
            img = f'<img src="{item["image_url"]}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-right:10px;">' if item.get('image_url') else ''
            size_txt = f' [সাইজ: {item["size"]}]' if item.get('size') else ''
            html += f'<div style="padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.1);">{img}<strong>{item["name"]}</strong>{size_txt} &times; {item["quantity"]} — ৳{item["total"]:.2f}</div>'
        html += '</div>'
        from django.utils.safestring import mark_safe
        return mark_safe(html)

    @admin.action(description="📧 নির্বাচিত কার্টগুলোতে রিকভারি ইমেইল পাঠান")
    def send_recovery_email_action(self, request, queryset):
        from .cart_recovery import send_abandoned_cart_email
        domain = request.build_absolute_uri('/')[:-1]
        sent = 0
        failed = 0
        for cart in queryset:
            success, msg = send_abandoned_cart_email(cart, domain=domain, force=True)
            if success:
                sent += 1
            else:
                failed += 1
        self.message_user(request, f"মোট {sent} টি ইমেইল পাঠানো হয়েছে। (ব্যর্থ/স্কিপ: {failed})")

    @admin.action(description="✅ রিকভার্ড হিসেবে চিহ্নিত করুন")
    def mark_as_recovered_action(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(is_recovered=True, recovered_at=timezone.now())
        self.message_user(request, f"{updated} টি কার্ট রিকভার্ড হিসেবে চিহ্নিত করা হয়েছে।")