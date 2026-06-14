from django.contrib import admin

from crm.models import AttendanceRecord, Course, Group, Lead, Student


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'price')
    list_filter = ('company',)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'course', 'status')
    list_filter = ('company', 'status')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'status', 'branch', 'group')
    list_filter = ('company', 'status')


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'stage', 'is_active', 'company')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'group', 'attend_date', 'status')
