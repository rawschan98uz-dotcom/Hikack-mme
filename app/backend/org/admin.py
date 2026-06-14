from django.contrib import admin

from org.models import Branch, Company, Room


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'subdomain', 'balance_mode', 'phone')
    search_fields = ('name', 'subdomain')


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'address')
    list_filter = ('company',)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'capacity')
