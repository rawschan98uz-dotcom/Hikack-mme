"""Finance rebuild, stage 1 (2026-10-05): a course price is valid from a date; only the CEO changes it."""
import datetime as dt
from datetime import date
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm import pricing
from crm.models import Course, CoursePrice, Group
from crm.pricing import price_on
from finance.models import SalarySetting
from operations.models import AuditLogRecord
from org.models import Branch, Company

TASHKENT = ZoneInfo('Asia/Tashkent')
TODAY = date(2026, 10, 5)


class Base(TestCase):
    def at(self, day: date):
        """Make the server clock show noon of `day` (Tashkent)."""
        patcher = mock.patch(
            'django.utils.timezone.now', return_value=dt.datetime(day.year, day.month, day.day, 12, 0, tzinfo=TASHKENT),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        pricing._synced_day = None  # the daily switch runs again on the next request
        return patcher

    def setUp(self):
        self.clock = self.at(TODAY)
        self.c = APIClient()
        self.company = Company.objects.create(name='Price Co', subdomain='priceco')
        self.a = Branch.objects.create(company=self.company, name='A')
        self.ceo = User.objects.create_user(phone='998905660001', password='x', first_name='Ceo', company=self.company,
                                            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO)
        self.admin = User.objects.create_user(phone='998905660002', password='x', first_name='Adm', company=self.company,
                                              user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR)
        self.course = Course.objects.create(company=self.company, name='а1', code='a1', price=500_000)
        # The course exists since 1 September
        CoursePrice.objects.filter(course=self.course).update(valid_from=date(2026, 9, 1))
        self.c.force_authenticate(self.ceo)

    def patch(self, **data):
        return self.c.patch(f'/v1/courses/{self.course.id}', data, format='json')

    def reload(self):
        self.course = Course.objects.get(pk=self.course.pk)
        return self.course


class PriceWithDateTests(Base):
    def test_new_course_gets_its_first_price_record(self):
        res = self.c.post('/v1/courses', {'name': 'b2', 'code': 'b2', 'price': 700_000}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        course = Course.objects.get(pk=res.json()['data']['id'])
        self.assertEqual(list(course.prices.values_list('price', 'valid_from')), [(700_000, TODAY)])
        # Days before the first record get the first price
        self.assertEqual(price_on(course, date(2020, 1, 1)), 700_000)

    def test_new_price_from_today_keeps_the_past(self):
        res = self.patch(price=600_000)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.reload().price, 600_000)
        self.assertEqual(price_on(self.course, date(2026, 10, 4)), 500_000)  # yesterday stays as it was
        self.assertEqual(price_on(self.course, TODAY), 600_000)
        self.assertEqual([h['price'] for h in res.json()['data']['price_history']], [500_000, 600_000])

    def test_planned_price_starts_on_its_day(self):
        res = self.patch(price=600_000, price_from='2026-11-01')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.reload().price, 500_000)  # nothing changes today
        self.assertEqual(res.json()['data']['next_price'], {'price': 600_000, 'valid_from': '2026-11-01'})
        self.assertEqual(price_on(self.course, date(2026, 10, 31)), 500_000)
        self.assertEqual(price_on(self.course, date(2026, 11, 1)), 600_000)

        self.clock.stop()
        self.at(date(2026, 11, 1))
        listed = self.c.get('/v1/courses').json()['data']  # the first request of 1 November
        row = next(r for r in listed if r['id'] == self.course.id)
        self.assertEqual((row['price'], row['next_price']), (600_000, None))
        self.assertEqual(self.reload().price, 600_000)

    def test_price_for_a_past_date(self):
        self.assertEqual(self.patch(price=400_000, price_from='2026-08-01').status_code, 200)
        self.assertEqual(self.patch(price=450_000, price_from='2026-09-15').status_code, 200)
        self.assertEqual(price_on(self.course, date(2026, 8, 20)), 400_000)
        self.assertEqual(price_on(self.course, date(2026, 9, 10)), 500_000)
        self.assertEqual(price_on(self.course, date(2026, 9, 20)), 450_000)
        self.assertEqual(self.reload().price, 450_000)  # the latest record that has started

    def test_same_day_twice_replaces_the_record(self):
        self.patch(price=600_000)
        self.patch(price=650_000)
        self.assertEqual(list(self.course.prices.values_list('price', flat=True)), [500_000, 650_000])
        self.assertEqual(self.reload().price, 650_000)

    def test_bad_price_is_refused(self):
        for bad in ('abc', -5, 500_000.5, 100_000_001):
            res = self.patch(price=bad)
            self.assertEqual(res.status_code, 400, bad)
        self.assertEqual(self.patch(price=600_000, price_from='не дата').status_code, 400)
        self.assertEqual(self.reload().price, 500_000)
        self.assertEqual(self.course.prices.count(), 1)

    def test_course_with_an_old_style_code_can_still_be_saved(self):
        # Real data: «а1» typed with a Cyrillic «а». The form sends the code with every save.
        Course.objects.filter(pk=self.course.pk).update(code='а1')
        res = self.patch(name='а1', code='а1', price=600_000)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.reload().price, 600_000)
        self.assertEqual(self.patch(code='б1').status_code, 400)  # a NEW code is still checked

    def test_price_saved_directly_is_kept_in_the_history(self):
        self.course.price = 700_000
        self.course.save()
        self.assertEqual(price_on(self.course, date(2026, 10, 4)), 500_000)
        self.assertEqual(price_on(self.course, TODAY), 700_000)

    def test_every_change_is_in_the_journal(self):
        self.patch(price=600_000, price_from='2026-11-01')
        log = AuditLogRecord.objects.get(entity_type='course', action='price_change')
        self.assertEqual(log.actor_id, self.ceo.id)
        self.assertIn('500 000 → 600 000', log.reason)
        self.assertIn('01.11.2026', log.reason)


class OnlyCeoTests(Base):
    def test_administrator_cannot_change_the_price(self):
        self.c.force_authenticate(self.admin)
        res = self.patch(price=1)
        self.assertEqual(res.status_code, 403)
        self.assertIn('только CEO', res.json()['message'])
        self.assertEqual(self.patch(price=600_000, price_from='2026-11-01').status_code, 403)
        self.assertEqual(self.reload().price, 500_000)
        self.assertEqual(self.course.prices.count(), 1)

    def test_administrator_still_edits_the_rest(self):
        self.c.force_authenticate(self.admin)
        # The edit form sends the unchanged price together with the other fields
        res = self.patch(name='а1 новый', price=500_000, description='Утро')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.reload().name, 'а1 новый')
        self.assertFalse(AuditLogRecord.objects.filter(entity_type='course').exists())

    def test_administrator_cannot_touch_the_history(self):
        entry = self.course.prices.get()
        self.c.force_authenticate(self.admin)
        url = f'/v1/courses/{self.course.id}/prices/{entry.id}'
        self.assertEqual(self.c.patch(url, {'price': 1}, format='json').status_code, 403)
        self.assertEqual(self.c.delete(url).status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.price, 500_000)


class FixHistoryTests(Base):
    def url(self, entry):
        return f'/v1/courses/{self.course.id}/prices/{entry.id}'

    def test_placeholder_price_is_fixed_for_all_the_past(self):
        # "500" was typed instead of the real price: fixing the record changes it for every past day too
        Course.objects.filter(pk=self.course.pk).update(price=500)
        entry = self.course.prices.get()
        CoursePrice.objects.filter(pk=entry.pk).update(price=500)
        res = self.c.patch(self.url(entry), {'price': 500_000}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.reload().price, 500_000)
        self.assertEqual(price_on(self.course, date(2026, 9, 17)), 500_000)
        self.assertEqual(self.course.prices.count(), 1)
        self.assertIn('Исправлена цена', AuditLogRecord.objects.get(action='price_fix').reason)

    def test_date_of_a_record_can_be_moved(self):
        self.patch(price=600_000, price_from='2026-11-01')
        planned = self.course.prices.get(price=600_000)
        res = self.c.patch(self.url(planned), {'valid_from': '2026-10-01'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.reload().price, 600_000)  # it has already started now
        self.assertEqual(price_on(self.course, date(2026, 9, 30)), 500_000)

    def test_two_prices_on_one_day_are_refused(self):
        self.patch(price=600_000, price_from='2026-11-01')
        planned = self.course.prices.get(price=600_000)
        res = self.c.patch(self.url(planned), {'valid_from': '2026-09-01'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_planned_price_can_be_removed_but_not_the_only_one(self):
        first = self.course.prices.get()
        self.assertEqual(self.c.delete(self.url(first)).status_code, 400)
        self.patch(price=600_000)
        todays = self.course.prices.get(price=600_000)
        self.assertEqual(self.c.delete(self.url(todays)).status_code, 200)
        self.assertEqual(self.reload().price, 500_000)
        self.assertTrue(AuditLogRecord.objects.filter(action='price_delete').exists())


class DeleteCourseTests(Base):
    def test_only_ceo_deletes_and_it_is_logged(self):
        self.c.force_authenticate(self.admin)
        self.assertEqual(self.c.delete(f'/v1/courses/{self.course.id}').status_code, 403)
        self.c.force_authenticate(self.ceo)
        self.assertEqual(self.c.delete(f'/v1/courses/{self.course.id}').status_code, 200)
        self.assertFalse(Course.objects.filter(pk=self.course.pk).exists())
        self.assertIn('Удалён курс', AuditLogRecord.objects.get(entity_type='course', action='delete').reason)

    def test_course_with_groups_is_not_deleted(self):
        group = Group.objects.create(company=self.company, branch=self.a, name='G', course=self.course)
        res = self.c.delete(f'/v1/courses/{self.course.id}')
        self.assertEqual(res.status_code, 400)
        group.refresh_from_db()
        self.assertEqual(group.course_id, self.course.id)  # the group keeps its price

    def test_course_with_a_teacher_percent_is_not_deleted(self):
        tom = User.objects.create_user(phone='998905660003', password='x', first_name='Tom', company=self.company,
                                       user_type=User.UserType.TEACHER)
        SalarySetting.objects.create(company=self.company, teacher=tom, teacher_name='Tom', salary_type='percent',
                                     amount=30, course=self.course)
        self.assertEqual(self.c.delete(f'/v1/courses/{self.course.id}').status_code, 400)
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())
