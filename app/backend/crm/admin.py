from django.contrib import admin

from crm.models import (
    AttendanceRecord,
    Course,
    Group,
    GroupEnrollment,
    GroupScheduleSlot,
    Lead,
    Student,
)



@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'price')
    list_filter = ('company',)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'course', 'status')
    list_filter = ('company', 'status')


@admin.register(GroupScheduleSlot)
class GroupScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ('group', 'weekday', 'start_time', 'end_time', 'room')
    list_filter = ('weekday',)


@admin.register(GroupEnrollment)
class GroupEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'group', 'status', 'joined_date', 'left_date')
    list_filter = ('company', 'status')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'photo', 'phone', 'status', 'branch', 'group', 'school')
    list_filter = ('company', 'status')

    def has_delete_permission(self, request, obj=None):
        # Owner's rule #10: students are archived ("Отчислить"), never erased — not even from the admin panel
        return False


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'stage', 'is_active', 'company')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'group', 'attend_date', 'status')

