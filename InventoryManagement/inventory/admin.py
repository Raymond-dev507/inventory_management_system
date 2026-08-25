from django.contrib import admin

# Register your models here.
from . models import Category,Supplier,Product,StockIn,StockOut,Sale,SaleItem,ActivityLog,AuthorizedTelegramUser,UserDeletionRecord
admin.site.register(Category)
admin.site.register(Supplier)
admin.site.register(Product)
admin.site.register(StockIn)
admin.site.register(StockOut)
admin.site.register(SaleItem)
admin.site.register(Sale)
admin.site.register(ActivityLog)
admin.site.register(UserDeletionRecord)


@admin.register(AuthorizedTelegramUser)
class AuthorizedTelegramUserAdmin(admin.ModelAdmin):
    list_display = (
        "telegram_username",
        "telegram_chat_id",
        "linked_user",
        "get_access_level",
        "is_active",
        "added_at",
    )
    list_filter = ("is_active",)
    autocomplete_fields = ("linked_user",)

    def get_access_level(self, obj):
        return (
            "Superuser (full access)"
            if obj.linked_user.is_superuser
            else "No access (not superuser)"
        )

    get_access_level.short_description = "Access level"