import os
import sys
from datetime import date, timedelta

# Ensure django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import django
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient

from org.models import Company, Branch, Room
from accounts.models import User, TeacherBranch
from crm.models import Course, Group, Student, Lead, AttendanceRecord, GroupScheduleSlot, GroupEnrollment
from finance.models import Payment, SalarySetting, PayrollPayment, Expense, ExpenseCategory
from crm.services import sync_group_schedule_slots, sync_student_paid_this_month


def run():
    print("=" * 60)
    print("НАЧАЛО ГЕНЕРАЦИИ ТЕСТОВЫХ ДАННЫХ В HIJACK LMS")
    print("=" * 60)

    # 1. Получение компании и филиала
    company = Company.objects.filter(id=1).first() or Company.objects.first()
    if not company:
        print("ОШИБКА: Компания не найдена!")
        return

    branch = Branch.objects.filter(company=company, id=1).first() or Branch.objects.filter(company=company).first()
    if not branch:
        branch = Branch.objects.create(company=company, name='Главный филиал')
    print(f"-> Компания: {company.name} (id={company.id})")
    print(f"-> Филиал: {branch.name} (id={branch.id})")

    # Получение пользователя CEO для APIClient
    ceo = User.objects.filter(company=company, staff_role=User.StaffRole.CEO).first()
    if not ceo:
        ceo = User.objects.filter(company=company).first()
    client = APIClient()
    client.force_authenticate(user=ceo)
    print(f"-> Авторизован как CEO: {ceo.display_name()} ({ceo.phone})")

    # 2. Проверка 3 предметов (Courses)
    courses_map = {}
    for c in Course.objects.filter(company=company):
        c_name = c.name.strip()
        courses_map[c_name] = c

    # Обеспечим Английский, Математика, Немецкий
    if 'Английский' not in courses_map:
        course_en = Course.objects.create(company=company, name='Английский', price=600000, lesson_duration=90, course_duration=12)
        courses_map['Английский'] = course_en
    if 'Математика' not in courses_map:
        course_math = Course.objects.create(company=company, name='Математика', price=500000, lesson_duration=90, course_duration=12)
        courses_map['Математика'] = course_math
    if 'Немецкий' not in courses_map:
        course_de = Course.objects.create(company=company, name='Немецкий', price=600000, lesson_duration=90, course_duration=12)
        courses_map['Немецкий'] = course_de

    course_en = courses_map['Английский']
    course_math = courses_map['Математика']
    course_de = courses_map['Немецкий']
    print(f"-> 3 Предмета готовы: Английский (id={course_en.id}), Математика (id={course_math.id}), Немецкий (id={course_de.id})")

    # 3. Создание 3 комнат (Rooms)
    rooms_data = [
        {'name': 'Кабинет 101 (Oxford)', 'capacity': 15},
        {'name': 'Кабинет 102 (Euler)', 'capacity': 15},
        {'name': 'Кабинет 103 (Berlin)', 'capacity': 12},
    ]
    rooms = []
    for rd in rooms_data:
        room = Room.objects.filter(branch=branch, name=rd['name']).first()
        if not room:
            room = Room.objects.create(branch=branch, name=rd['name'], capacity=rd['capacity'])
        rooms.append(room)
        print(f"-> Комната: {room.name} (вместимость {room.capacity})")

    # 4. Создание 3 учителей (Teachers)
    teachers_data = [
        {
            'first_name': 'Азизбек',
            'last_name': 'Рахимов',
            'phone': '901001122',
            'job_title': 'Преподаватель английского языка',
            'honorific': 'Mr',
            'salary': 4000000,
        },
        {
            'first_name': 'Нилуфар',
            'last_name': 'Каримова',
            'phone': '902002233',
            'job_title': 'Преподаватель математики',
            'honorific': 'Ms',
            'salary': 3500000,
        },
        {
            'first_name': 'Джамшид',
            'last_name': 'Холматов',
            'phone': '903003344',
            'job_title': 'Преподаватель немецкого языка',
            'honorific': 'Mr',
            'salary': 3800000,
        },
    ]
    teachers = []
    for td in teachers_data:
        teacher = User.objects.filter(company=company, phone=td['phone']).first()
        if not teacher:
            teacher = User.objects.create_user(
                phone=td['phone'],
                password='password123',
                first_name=td['first_name'],
                last_name=td['last_name'],
                company=company,
                user_type=User.UserType.TEACHER,
                job_title=td['job_title'],
                honorific=td['honorific'],
            )
        TeacherBranch.objects.get_or_create(teacher=teacher, branch=branch)
        teachers.append((teacher, td['salary']))
        print(f"-> Учитель: {teacher.display_name()} ({td['job_title']}, тел. {teacher.phone})")

    # 5. Создание 3 групп (Groups)
    from datetime import time
    groups_data = [
        {
            'name': 'English Elementary (A1)',
            'course': course_en,
            'teacher': teachers[0][0],
            'room': rooms[0],
            'days': Group.Days.ODD,  # Пн/Ср/Пт
            'start_time': time(9, 0),
            'end_time': time(10, 30),
            'start_date': date(2026, 9, 1),
            'end_date': date(2027, 5, 31),
        },
        {
            'name': 'Математика Базовая',
            'course': course_math,
            'teacher': teachers[1][0],
            'room': rooms[1],
            'days': Group.Days.EVEN,  # Вт/Чт/Сб
            'start_time': time(14, 0),
            'end_time': time(15, 30),
            'start_date': date(2026, 9, 1),
            'end_date': date(2027, 5, 31),
        },
        {
            'name': 'Deutsch A1 (Abend)',
            'course': course_de,
            'teacher': teachers[2][0],
            'room': rooms[2],
            'days': Group.Days.ODD,  # Пн/Ср/Пт
            'start_time': time(17, 0),
            'end_time': time(18, 30),
            'start_date': date(2026, 9, 1),
            'end_date': date(2027, 5, 31),
        },
    ]

    groups = []
    for gd in groups_data:
        grp = Group.objects.filter(company=company, name=gd['name']).first()
        if not grp:
            grp = Group.objects.create(
                company=company,
                branch=branch,
                name=gd['name'],
                course=gd['course'],
                teacher=gd['teacher'],
                room=gd['room'],
                days=gd['days'],
                status=Group.Status.ACTIVE,
                lesson_start_time=gd['start_time'],
                lesson_end_time=gd['end_time'],
                group_start_date=gd['start_date'],
                group_end_date=gd['end_date'],
            )
        sync_group_schedule_slots(grp)
        groups.append(grp)
        print(f"-> Группа: {grp.name} | Преподаватель: {grp.teacher.display_name()} | Кабинет: {grp.room.name}")

    # 6. Создание 30 студентов ЧЕРЕЗ API
    # 15 юношей и 15 девушек. Включая родственников (братья/сестры) и однофамильцев/тёзок
    students_data = [
        # --- ГРУППА 1: English Elementary (A1) [9 студентов] ---
        # 1. Рустам Каримов (Брат Зарины Каримовой, семейный тел 901112233)
        {
            'first_name': 'Рустам', 'last_name': 'Каримов', 'phone': '901112233',
            'phone2': '909998877', 'phone2_owner': 'Отец',
            'address': 'г. Ташкент, Чиланзар-9, д. 15, кв. 42', 'school': 'Школа № 173',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Старший брат Зарины Каримовой. Отличная посещаемость.'
        },
        # 2. Санжар Умаров (Брат Сардора Умарова, семейный тел 935551122 - ДОЛЖНИК)
        {
            'first_name': 'Санжар', 'last_name': 'Умаров', 'phone': '935551122',
            'phone2': '931110022', 'phone2_owner': 'Мама',
            'address': 'г. Ташкент, Юнусабад-11, д. 4', 'school': 'Школа № 257',
            'group_id': groups[0].id, 'is_debtor': True, 'payment_amount': 0,
            'comment': 'Брат Сардора. Долг за сентябрь, мама обещала внести оплату в конце недели.'
        },
        # 3. Шахзод Алиев (Семья Алиевых: брат лида Нигины Алиевой, семейный тел 946663344)
        {
            'first_name': 'Шахзод', 'last_name': 'Алиев', 'phone': '946663344',
            'phone2': '903334411', 'phone2_owner': 'Отец',
            'address': 'г. Ташкент, Мирзо-Улугбек, ул. Буюк Ипак Йули 88', 'school': 'Лицей при УМЭД',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Родной брат лида Нигины. Изучает английский для IELTS.'
        },
        # 4. Жасур Юлдашев (Тёзка 1, тел 901230001)
        {
            'first_name': 'Жасур', 'last_name': 'Юлдашев', 'phone': '901230001',
            'address': 'г. Ташкент, Шайхантахур, массив Ц-14', 'school': 'Школа № 42',
            'group_id': groups[0].id, 'is_debtor': True, 'payment_amount': 0,
            'comment': 'Полный тёзка студента из группы математики. Задолженность за сентябрь.'
        },
        # 5. Алишер Махмудов (Однофамилец лида Алишера Махмудова, тел 905550011)
        {
            'first_name': 'Алишер', 'last_name': 'Махмудов', 'phone': '905550011',
            'address': 'г. Ташкент, Мирабад, ул. Нукус 21', 'school': 'Школа № 60',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Успешно учится, активен на уроках.'
        },
        # 6. Малика Саидова (девушка)
        {
            'first_name': 'Малика', 'last_name': 'Саидова', 'phone': '907772211',
            'address': 'г. Ташкент, Яккасарай, ул. Шота Руставели 45', 'school': 'Школа № 144',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Прилежная ученица, высокий балл по тестам.'
        },
        # 7. Севара Ибрагимова (девушка)
        {
            'first_name': 'Севара', 'last_name': 'Ибрагимова', 'phone': '913334455',
            'address': 'г. Ташкент, Алмазар, Каракамыш 2/4', 'school': 'Школа № 28',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Посещает все занятия без пропусков.'
        },
        # 8. Бехзод Турсунов (юноша)
        {
            'first_name': 'Бехзод', 'last_name': 'Турсунов', 'phone': '934445566',
            'address': 'г. Ташкент, Учтепа, 26 квартал', 'school': 'Школа № 197',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Готовится к поступлению в лицей.'
        },
        # 9. Дилноза Ахмедова (девушка)
        {
            'first_name': 'Дилноза', 'last_name': 'Ахмедова', 'phone': '995556677',
            'address': 'г. Ташкент, Яшнабад, ул. Паркентская 12', 'school': 'Школа № 166',
            'group_id': groups[0].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Оплата внесена на месяц вперед.'
        },

        # --- ГРУППА 2: Математика Базовая [9 студентов] ---
        # 10. Сардор Умаров (Брат Санжара Умарова, семейный тел 935551122)
        {
            'first_name': 'Сардор', 'last_name': 'Умаров', 'phone': '935551122',
            'phone2': '931110022', 'phone2_owner': 'Мама',
            'address': 'г. Ташкент, Юнусабад-11, д. 4', 'school': 'Школа № 257',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Старший брат Санжара Умарова. Математика дается отлично.'
        },
        # 11. Жасур Юлдашев (Тёзка 2, тел 901230002)
        {
            'first_name': 'Жасур', 'last_name': 'Юлдашев', 'phone': '901230002',
            'address': 'г. Ташкент, Чиланзар-2, д. 8', 'school': 'Школа № 103',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Полный тёзка студента из группы английского. Оплачено вовремя.'
        },
        # 12. Малика Каримова (Однофамилица Каримовых, отдельная семья, тел 912223344)
        {
            'first_name': 'Малика', 'last_name': 'Каримова', 'phone': '912223344',
            'address': 'г. Ташкент, Яккасарай, ул. Бабура 15', 'school': 'Лицей при ВЕСТ',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Однофамилица из Яккасарая. Готовится к олимпиадам.'
        },
        # 13. Бобур Алиев (Однофамилец Алиевых, отдельная семья, тел 907771122)
        {
            'first_name': 'Бобур', 'last_name': 'Алиев', 'phone': '907771122',
            'address': 'г. Ташкент, Сергели-7, д. 23', 'school': 'Школа № 301',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Сильный ученик, решает нестандартные задачи.'
        },
        # 14. Камила Назарова (девушка - ДОЛЖНИК)
        {
            'first_name': 'Камила', 'last_name': 'Назарова', 'phone': '908889900',
            'phone2': '901114477', 'phone2_owner': 'Мама',
            'address': 'г. Ташкент, Мирзо-Улугбек, Карасу-1', 'school': 'Школа № 208',
            'group_id': groups[1].id, 'is_debtor': True, 'payment_amount': 0,
            'comment': 'Задержка оплаты за сентябрь. Звонили маме.'
        },
        # 15. Темур Шарипов (юноша)
        {
            'first_name': 'Темур', 'last_name': 'Шарипов', 'phone': '941112299',
            'address': 'г. Ташкент, Шайхантахур, массив Лабзак', 'school': 'Школа № 41',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Хорошая дисциплина и оценки.'
        },
        # 16. Азиза Хасанова (девушка)
        {
            'first_name': 'Азиза', 'last_name': 'Хасанова', 'phone': '972223388',
            'address': 'г. Ташкент, Чиланзар-16, д. 3', 'school': 'Школа № 217',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Оплачено через Payme.'
        },
        # 17. Мурод Закиров (юноша)
        {
            'first_name': 'Мурод', 'last_name': 'Закиров', 'phone': '983334477',
            'address': 'г. Ташкент, Юнусабад-15, д. 29', 'school': 'Школа № 97',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Регулярно делает домашние задания.'
        },
        # 18. Нилуфар Касымова (девушка)
        {
            'first_name': 'Нилуфар', 'last_name': 'Касымова', 'phone': '994445588',
            'address': 'г. Ташкент, Алмазар, Себзар', 'school': 'Школа № 1',
            'group_id': groups[1].id, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Занимается с интересом.'
        },

        # --- ГРУППА 3: Deutsch A1 (Abend) [8 студентов] ---
        # 19. Зарина Каримова (Сестра Рустама Каримова, семейный тел 901112233)
        {
            'first_name': 'Зарина', 'last_name': 'Каримова', 'phone': '901112233',
            'phone2': '909998877', 'phone2_owner': 'Отец',
            'address': 'г. Ташкент, Чиланзар-9, д. 15, кв. 42', 'school': 'Школа № 173',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Младшая сестра Рустама Каримова. Изучает немецкий для учебы в Германии.'
        },
        # 20. Азиз Каримов (Однофамилец Каримовых из Сергели, тел 909990011)
        {
            'first_name': 'Азиз', 'last_name': 'Каримов', 'phone': '909990011',
            'address': 'г. Ташкент, Сергели-4, д. 11', 'school': 'Школа № 300',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Однофамилец из Сергели. Быстро осваивает разговорную речь.'
        },
        # 21. Достон Расулов (юноша)
        {
            'first_name': 'Достон', 'last_name': 'Расулов', 'phone': '905556611',
            'address': 'г. Ташкент, Мирабад, ул. Афросиаб 14', 'school': 'Школа № 110',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Усердно занимается произношением.'
        },
        # 22. Шахло Рустамова (девушка)
        {
            'first_name': 'Шахло', 'last_name': 'Рустамова', 'phone': '916667722',
            'address': 'г. Ташкент, Учтепа, Чиланзар-12', 'school': 'Школа № 228',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Оплата внесена картой.'
        },
        # 23. Фаррух Мирзаев (юноша)
        {
            'first_name': 'Фаррух', 'last_name': 'Мирзаев', 'phone': '937778833',
            'address': 'г. Ташкент, Шайхантахур, массив Бешагач', 'school': 'Школа № 84',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Планирует сдавать Goethe-Zertifikat A1.'
        },
        # 24. Гульноза Султанова (девушка)
        {
            'first_name': 'Гульноза', 'last_name': 'Султанова', 'phone': '948889944',
            'address': 'г. Ташкент, Юнусабад-4, д. 16', 'school': 'Школа № 246',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Все домашние работы сдаются вовремя.'
        },
        # 25. Отабек Баходиров (юноша)
        {
            'first_name': 'Отабек', 'last_name': 'Баходиров', 'phone': '979990055',
            'address': 'г. Ташкент, Яккасарай, ул. Кичик Бешагач', 'school': 'Школа № 89',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Оплата наличными через кассу.'
        },
        # 26. Райхон Джураева (девушка)
        {
            'first_name': 'Райхон', 'last_name': 'Джураева', 'phone': '991112266',
            'address': 'г. Ташкент, Мирзо-Улугбек, Ц-2', 'school': 'Школа № 64',
            'group_id': groups[2].id, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Активная участница дискуссий на немецком.'
        },

        # --- СТУДЕНТЫ БЕЗ ГРУППЫ (для тестирования ручного распределения) [4 студента] ---
        # 27. Даврон Юнусов (юноша)
        {
            'first_name': 'Даврон', 'last_name': 'Юнусов', 'phone': '902223301',
            'address': 'г. Ташкент, Чиланзар-20', 'school': 'Школа № 238',
            'group_id': None, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Ожидает открытия утренней группы английского.'
        },
        # 28. Мадина Темирова (девушка - ДОЛЖНИК)
        {
            'first_name': 'Мадина', 'last_name': 'Темирова', 'phone': '913334402',
            'address': 'г. Ташкент, Юнусабад-19', 'school': 'Школа № 272',
            'group_id': None, 'is_debtor': True, 'payment_amount': 0,
            'comment': 'Не распределена по расписанию. Долг за регистрационный сбор.'
        },
        # 29. Лола Сафарова (девушка)
        {
            'first_name': 'Лола', 'last_name': 'Сафарова', 'phone': '934445503',
            'address': 'г. Ташкент, Мирабад, Госпитальный массив', 'school': 'Школа № 94',
            'group_id': None, 'is_debtor': False, 'payment_amount': 500000,
            'comment': 'Выбирает между математикой и немецким.'
        },
        # 30. Ясмина Валиева (девушка)
        {
            'first_name': 'Ясмина', 'last_name': 'Валиева', 'phone': '975556604',
            'address': 'г. Ташкент, Сергели-2', 'school': 'Школа № 55',
            'group_id': None, 'is_debtor': False, 'payment_amount': 600000,
            'comment': 'Записалась недавно, согласовывает дни занятий.'
        },
    ]

    created_students = []
    print("\n--- СОЗДАНИЕ 30 УЧЕНИКОВ ЧЕРЕЗ API ---")
    for i, sd in enumerate(students_data, 1):
        post_data = {
            'first_name': sd['first_name'],
            'last_name': sd['last_name'],
            'phone': sd['phone'],
            'phone2': sd.get('phone2', ''),
            'phone2_owner': sd.get('phone2_owner', ''),
            'address': sd.get('address', ''),
            'school': sd.get('school', ''),
            'comment': sd.get('comment', ''),
            'branch_id': branch.id,
            'group_id': sd.get('group_id'),
            'trial_date': '2026-09-01',
            'status': Student.Status.STUDYING,
        }
        res = client.post('/v1/students', post_data, format='json')
        if res.status_code == 201:
            st_id = res.json()['data']['id']
            student = Student.objects.get(pk=st_id)
            created_students.append((student, sd))
            gender = 'Девушка' if sd['first_name'] in ['Зарина', 'Малика', 'Севара', 'Дилноза', 'Камила', 'Азиза', 'Нилуфар', 'Шахло', 'Гульноза', 'Райхон', 'Мадина', 'Лола', 'Ясмина'] else 'Юноша'
            grp_name = student.group.name if student.group else 'Без группы'
            print(f"[{i:02d}/30] [УСПЕХ 201] {student.full_name} ({gender}) | Тел: {student.phone} | Группа: {grp_name}")
        else:
            print(f"[{i:02d}/30] [ОШИБКА {res.status_code}] {sd['first_name']} {sd['last_name']} ({sd['phone']}): {res.content.decode('utf-8')}")

    # 7. Создание оплат студентов (Payments) и настройка должников
    print("\n--- ПРОВЕДЕНИЕ ОПЛАТ СТУДЕНТОВ И РАСЧЕТ ДОЛГОВ ---")
    debtor_count = 0
    paid_count = 0
    methods = [Payment.Method.CASH, Payment.Method.CARD, Payment.Method.TRANSFER]

    for idx, (student, sd) in enumerate(created_students):
        if sd['is_debtor']:
            # Настраиваем должника: отрицательный баланс, paid_this_month = False
            student.balance = - (student.group.course.price if student.group and student.group.course else 500000)
            student.paid_this_month = False
            student.save(update_fields=['balance', 'paid_this_month'])
            debtor_count += 1
            print(f"-> Должник: {student.full_name} (Баланс: {student.balance:,} UZS, оплата в тек. месяце: НЕТ)")
        else:
            amt = sd['payment_amount']
            method = methods[idx % len(methods)]
            p_res = client.post('/v1/replenishments', {
                'student_id': student.id,
                'amount': amt,
                'method': method,
                'months_covered': 1,
                'comment': f'Оплата за обучение за сентябрь 2026 ({method})',
            }, format='json')
            if p_res.status_code == 200:
                student.refresh_from_db()
                student.balance = 0
                student.paid_this_month = True
                student.save(update_fields=['balance', 'paid_this_month'])
                paid_count += 1
                print(f"-> Оплата: {student.full_name} — {amt:,} UZS ({method}) [Успешно]")
            else:
                print(f"-> Ошибка оплаты {student.full_name}: {p_res.content.decode('utf-8')}")

    print(f"Всего оплативших: {paid_count}, Должников: {debtor_count}")

    # 8. Создание 15 лидов ЧЕРЕЗ API (по 5 на каждый из 3 этапов)
    leads_data = [
        # --- ЭТАП 1: trial_booked («Записан на пробный») [5 лидов] ---
        # 1. Нигина Алиева (Сестра студента Шахзода Алиева, семейный тел 946663344)
        {
            'first_name': 'Нигина', 'last_name': 'Алиева', 'phone': '946663344',
            'phone2': '903334411', 'phone2_owner': 'Отец',
            'address': 'г. Ташкент, Мирзо-Улугбек, ул. Буюк Ипак Йули 88', 'school': 'Школа № 142',
            'course_id': course_en.id, 'stage': Lead.Stage.TRIAL_BOOKED, 'source': 'Рекомендация',
            'trial_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'comment': 'Младшая сестра студента Шахзода Алиева. Записана на пробный по английскому.'
        },
        # 2. Лола Рахимова (Сестра лида Дилшода Рахимова, семейный тел 978884455)
        {
            'first_name': 'Лола', 'last_name': 'Рахимова', 'phone': '978884455',
            'phone2': '901239988', 'phone2_owner': 'Мама',
            'address': 'г. Ташкент, Юнусабад-8, д. 19', 'school': 'Школа № 260',
            'course_id': course_de.id, 'stage': Lead.Stage.TRIAL_BOOKED, 'source': 'Instagram',
            'trial_date': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'comment': 'Сестра лида Дилшода Рахимова. Записана на пробный по немецкому.'
        },
        # 3. Темур Исмаилов
        {
            'first_name': 'Темур', 'last_name': 'Исмаилов', 'phone': '903332211',
            'address': 'г. Ташкент, Чиланзар-5', 'school': 'Школа № 162',
            'course_id': course_math.id, 'stage': Lead.Stage.TRIAL_BOOKED, 'source': 'Telegram',
            'trial_date': (timezone.localdate() + timedelta(days=3)).isoformat(),
            'comment': 'Интересуется подготовкой к вступительным экзаменам.'
        },
        # 4. Камила Назарова (Лид-тёзка студентки)
        {
            'first_name': 'Камила', 'last_name': 'Назарова', 'phone': '914445566',
            'address': 'г. Ташкент, Яккасарай', 'school': 'Школа № 91',
            'course_id': course_en.id, 'stage': Lead.Stage.TRIAL_BOOKED, 'source': 'Сайт',
            'trial_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'comment': 'Оставила заявку на сайте на пробный урок.'
        },
        # 5. Мурод Хакимов
        {
            'first_name': 'Мурод', 'last_name': 'Хакимов', 'phone': '937778899',
            'address': 'г. Ташкент, Учтепа-11', 'school': 'Школа № 78',
            'course_id': course_math.id, 'stage': Lead.Stage.TRIAL_BOOKED, 'source': 'Листовка',
            'trial_date': (timezone.localdate() + timedelta(days=4)).isoformat(),
            'comment': 'Получил флаер возле школы.'
        },

        # --- ЭТАП 2: attended («Был на уроке / Думает») [5 лидов] ---
        # 6. Дилшод Рахимов (Брат Лолы Рахимовой, семейный тел 978884455)
        {
            'first_name': 'Дилшод', 'last_name': 'Рахимов', 'phone': '978884455',
            'phone2': '901239988', 'phone2_owner': 'Мама',
            'address': 'г. Ташкент, Юнусабад-8, д. 19', 'school': 'Школа № 260',
            'course_id': course_de.id, 'stage': Lead.Stage.ATTENDED, 'source': 'Instagram',
            'trial_date': (timezone.localdate() - timedelta(days=2)).isoformat(),
            'comment': 'Брат Лолы. Был на пробном уроке у Джамшида, очень понравилось, думает над расписанием.'
        },
        # 7. Бобур Ахмедов
        {
            'first_name': 'Бобур', 'last_name': 'Ахмедов', 'phone': '951112233',
            'address': 'г. Ташкент, Шайхантахур', 'school': 'Школа № 19',
            'course_id': course_en.id, 'stage': Lead.Stage.ATTENDED, 'source': 'Telegram',
            'trial_date': (timezone.localdate() - timedelta(days=3)).isoformat(),
            'comment': 'Был на пробном, просил вечернюю группу.'
        },
        # 8. Севара Мирзаева
        {
            'first_name': 'Севара', 'last_name': 'Мирзаева', 'phone': '992223344',
            'address': 'г. Ташкент, Мирабад', 'school': 'Школа № 328',
            'course_id': course_math.id, 'stage': Lead.Stage.ATTENDED, 'source': 'Рекомендация',
            'trial_date': (timezone.localdate() - timedelta(days=1)).isoformat(),
            'comment': 'Пробный прошел успешно, согласовывает оплату с родителями.'
        },
        # 9. Достон Касымов
        {
            'first_name': 'Достон', 'last_name': 'Касымов', 'phone': '904443322',
            'address': 'г. Ташкент, Сергели', 'school': 'Школа № 6',
            'course_id': course_en.id, 'stage': Lead.Stage.ATTENDED, 'source': 'Instagram',
            'trial_date': (timezone.localdate() - timedelta(days=4)).isoformat(),
            'comment': 'Выбирает между групповыми и индивидуальными занятиями.'
        },
        # 10. Шахло Рустамова (Лид-однофамилица студентки)
        {
            'first_name': 'Шахло', 'last_name': 'Рустамова', 'phone': '938887766',
            'address': 'г. Ташкент, Алмазар', 'school': 'Школа № 24',
            'course_id': course_de.id, 'stage': Lead.Stage.ATTENDED, 'source': 'Сайт',
            'trial_date': (timezone.localdate() - timedelta(days=2)).isoformat(),
            'comment': 'Ждет начисления стипендии 25 числа для оплаты курса.'
        },

        # --- ЭТАП 3: rejected («Отказ») [5 лидов] ---
        # 11. Алишер Махмудов (Тёзка студента Алишера Махмудова, тел 905550022)
        {
            'first_name': 'Алишер', 'last_name': 'Махмудов', 'phone': '905550022',
            'address': 'г. Ташкент, Бектемирский р-н', 'school': 'Школа № 289',
            'course_id': course_en.id, 'stage': Lead.Stage.REJECTED, 'source': 'Листовка',
            'comment': 'Отказ: Слишком далеко добираться до филиала из Бектемира.'
        },
        # 12. Отабек Салимов
        {
            'first_name': 'Отабек', 'last_name': 'Салимов', 'phone': '916667788',
            'address': 'г. Ташкент, Яшнабад', 'school': 'Школа № 153',
            'course_id': course_math.id, 'stage': Lead.Stage.REJECTED, 'source': 'Instagram',
            'comment': 'Отказ: Не подошло расписание (хотел занятия только по воскресеньям).'
        },
        # 13. Райхон Эргашева
        {
            'first_name': 'Райхон', 'last_name': 'Эргашева', 'phone': '971112233',
            'address': 'г. Ташкент, Юнусабад', 'school': 'Школа № 51',
            'course_id': course_de.id, 'stage': Lead.Stage.REJECTED, 'source': 'Telegram',
            'comment': 'Отказ: Передумали, записались на курсы рядом с домом.'
        },
        # 14. Даврон Холматов
        {
            'first_name': 'Даврон', 'last_name': 'Холматов', 'phone': '942223355',
            'address': 'г. Ташкент, Чиланзар', 'school': 'Школа № 182',
            'course_id': course_en.id, 'stage': Lead.Stage.REJECTED, 'source': 'Сайт',
            'comment': 'Отказ: Высокая стоимость обучения, ищут бюджетный вариант.'
        },
        # 15. Зиёда Баходирова
        {
            'first_name': 'Зиёда', 'last_name': 'Баходирова', 'phone': '983334455',
            'address': 'г. Ташкент, Учтепа', 'school': 'Школа № 107',
            'course_id': course_math.id, 'stage': Lead.Stage.REJECTED, 'source': 'Рекомендация',
            'comment': 'Отказ: Семья переезжает в Самарканд.'
        },
    ]

    print("\n--- СОЗДАНИЕ 15 ЛИДОВ ЧЕРЕЗ API ---")
    for i, ld in enumerate(leads_data, 1):
        post_data = {
            'first_name': ld['first_name'],
            'last_name': ld['last_name'],
            'phone': ld['phone'],
            'phone2': ld.get('phone2', ''),
            'phone2_owner': ld.get('phone2_owner', ''),
            'address': ld.get('address', ''),
            'school': ld.get('school', ''),
            'course_id': ld.get('course_id'),
            'branch_id': branch.id,
            'stage': ld['stage'],
            'source': ld.get('source', ''),
            'trial_date': ld.get('trial_date', timezone.localdate().isoformat()),
            'comment': ld.get('comment', ''),
        }
        res = client.post('/v1/leads', post_data, format='json')
        if res.status_code == 201:
            lead_id = res.json()['data']['id']
            lead = Lead.objects.get(pk=lead_id)
            if ld['stage'] == Lead.Stage.ATTENDED:
                lead.attended_trial = True
                lead.stage = Lead.Stage.ATTENDED
                lead.save(update_fields=['attended_trial', 'stage'])
            print(f"[{i:02d}/15] [УСПЕХ 201] Лид: {lead.full_name} | Этап: {lead.stage} | Тел: {lead.phone}")
        else:
            print(f"[{i:02d}/15] [ОШИБКА {res.status_code}] {ld['first_name']} {ld['last_name']}: {res.content.decode('utf-8')}")

    # 9. Настройка окладов и выплат преподавателям (Teacher Salary & Payroll)
    print("\n--- НАСТРОЙКА ОКЛАДОВ И ВЫПЛАТ УЧИТЕЛЯМ (PAYROLL) ---")
    exp_cat, _ = ExpenseCategory.objects.get_or_create(company=company, name='Зарплата преподавателей')

    for teacher, salary in teachers:
        # 1. Salary Setting
        SalarySetting.objects.update_or_create(
            company=company,
            teacher=teacher,
            defaults={
                'teacher_name': teacher.display_name(),
                'salary_type': SalarySetting.SalaryType.FIXED,
                'amount': salary,
                'effective_from': date(2026, 9, 1),
                'created_by': ceo,
            }
        )

        # 2. Выплата зарплаты за сентябрь 2026 (Expense + PayrollPayment)
        paid_amount = int(salary * 0.5)  # Аванс 50%
        expense = Expense.objects.create(
            company=company,
            category=exp_cat,
            description=f'Аванс за сентябрь 2026: {teacher.display_name()}',
            payee=teacher.display_name(),
            amount=paid_amount,
            method=Expense.Method.CARD,
            created_by=ceo,
        )
        pp = PayrollPayment.objects.create(
            company=company,
            teacher=teacher,
            payroll_period='2026-09',
            amount=paid_amount,
            method=PayrollPayment.Method.CARD,
            comment=f'Выплата аванса за сентябрь 2026 ({paid_amount:,} UZS)',
            expense=expense,
            created_by=ceo,
        )
        print(f"-> Учитель {teacher.display_name()}: оклад {salary:,} UZS/мес. Выплачен аванс: {pp.amount:,} UZS (Payroll id={pp.id})")

    # 10. Посещаемость (Attendance Records) для наполнения отчетов
    print("\n--- СОЗДАНИЕ ЖУРНАЛА ПОСЕЩАЕМОСТИ (ATTENDANCE) ---")
    dates_to_mark = [
        date(2026, 9, 2),
        date(2026, 9, 4),
        date(2026, 9, 7),
        date(2026, 9, 9),
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 16),
        date(2026, 9, 18),
    ]

    att_count = 0
    for grp in groups:
        students_in_grp = list(Student.objects.filter(group=grp, status=Student.Status.STUDYING))
        for dt in dates_to_mark:
            for s_idx, st in enumerate(students_in_grp):
                # Большинство PRESENT (1), несколько LATE (2) или ABSENT (0)
                if (s_idx + dt.day) % 11 == 0:
                    status = AttendanceRecord.Status.ABSENT
                    note = 'Уважительная причина (справка)'
                elif (s_idx + dt.day) % 7 == 0:
                    status = AttendanceRecord.Status.LATE
                    note = 'Опоздание на 15 мин'
                else:
                    status = AttendanceRecord.Status.PRESENT
                    note = ''

                AttendanceRecord.objects.update_or_create(
                    company=company,
                    group=grp,
                    student=st,
                    attend_date=dt,
                    defaults={'status': status, 'note': note}
                )
                att_count += 1

    print(f"Создано записей в журнале посещаемости: {att_count}")

    print("\n" + "=" * 60)
    print("ГЕНЕРАЦИЯ ДАННЫХ УСПЕШНО ЗАВЕРШЕНА!")
    print(f"Учеников: {Student.objects.filter(company=company).count()}")
    print(f"Лидов: {Lead.objects.filter(company=company).count()}")
    print(f"Групп: {Group.objects.filter(company=company).count()}")
    print(f"Учителей: {User.objects.filter(company=company, user_type=User.UserType.TEACHER).count()}")
    print(f"Платежей студентов: {Payment.objects.filter(company=company).count()}")
    print("=" * 60)


if __name__ == '__main__':
    run()
