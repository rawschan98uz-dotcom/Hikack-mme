# Архитектурный обзор: Teachers & Groups (Учителя и Группы)

Данный документ предназначен для быстрого погружения любой LLM (ChatGPT, Claude, Gemini, DeepSeek) в контекст подсистемы учителей и учебных групп образовательного CRM/LMS Hijack-MME.

---

## 1. Концепция и ключевые сущности

```
                     ┌──────────────────┐
                     │   org.Company    │
                     └────────┬─────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       ┌──────────────┐                ┌──────────────┐
       │  org.Branch  │                │  crm.Course  │
       └──────┬───────┘                └──────┬───────┘
              │                               │
              │  ┌─────────────────────────┐  │
              ├──┤ accounts.User (TEACHER) │  │
              │  └────────────┬────────────┘  │
              │               │               │
              │               ▼               │
              │        ┌──────────────┐       │
              ├───────►│  crm.Group   │◄──────┘
              │        └──────┬───────┘
              ▼               │
       ┌──────────────┐       │
       │   org.Room   │◄──────┤ (Кабинет группы)
       └──────────────┘       │
                              ▼
                       ┌──────────────┐
                       │ crm.Student  │ (Студенты группы)
                       └──────┬───────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
  ┌────────────────────────┐      ┌────────────────────────┐
  │  crm.AttendanceRecord  │      │ operations.Teacher-    │
  │  (Посещаемость студента│      │ AttendanceRecord       │
  │   в группе)            │      │ (Посещаемость учителя) │
  └────────────────────────┘      └────────────────────────┘
```

### 1.1 Модели данных
1. **`accounts.User` (Учитель)**:
   - Роль определяется полем `user_type = User.UserType.TEACHER`.
   - Имеет поля `first_name`, `last_name`, `phone`, `honorific` (обращение: Mr, Ms, Teacher и т.д.), `job_title`, `is_active`.
   - Привязка к филиалам: через модель `TeacherBranch(teacher, branch)`.
2. **`crm.Group` (Группа)**:
   - Поля: `company`, `branch`, `course` (FK на Course), `teacher` (FK на User TEACHER), `room` (FK на org.Room), `name`.
   - Расписание: `days` (JSON массив дней недели, например `["mon", "wed", "fri"]`), `start_time`, `end_time`, `start_date`, `end_date`.
   - Статус: `status = 2` (ACTIVE), `3` (ARCHIVE).
   - Теги: `tags` (JSON массив).
3. **`crm.Course` (Курс)**:
   - `name`, `code`, `price` (стоимость курса в месяц), `lesson_duration` (мин, по дефолту 90), `course_duration` (мес, по дефолту 12).
4. **`org.Room` (Кабинет)**:
   - `company`, `branch`, `name`, `capacity`.
5. **`crm.Student` (Студент в группе)**:
   - `group` (FK на `crm.Group`, `on_delete=models.SET_NULL`).
   - При удалении/отчислении студента (`status = Student.Status.LEFT`), `group` сбрасывается в `None`.
6. **`crm.AttendanceRecord` (Журнал посещаемости студентов)**:
   - `student`, `group`, `date`, `status` (1=Present, 2=Absent, 3=Excused, 4=Late), `comment`.
   - **Бизнес-правило P2**: `student.group_id == group.id` и `student.company_id == group.company_id`.
7. **`operations.TeacherAttendanceRecord` (Посещаемость учителей)**:
   - `teacher`, `group`, `company`, `attend_date`, `status` (1=Present, 2=Absent, 3=Late), `notes`.
   - Уникальность: `unique_together = [['company', 'teacher', 'group', 'attend_date']]`.
8. **`finance.SalarySetting` (Ставки зарплаты учителей)**:
   - `salary_type`: `FIXED` (фиксированный оклад), `PERCENT` (% от оплат студентов группы), `PER_STUDENT` (фикс за каждого активного студента).
   - `amount`: числовое значение (ставка или %).
   - `teacher_name`: ФИО учителя.

---

## 2. API Эндпоинты (Backend)

| Маршрут | Методы | Назначение | Контроллер |
|---|---|---|---|
| `/v1/groups` | `GET`, `POST` | Список групп (фильтры по филиалу, учителю, курсу, статусу) / создание группы | `api.v1.views.group_list` |
| `/v1/groups/<id>` | `GET`, `PATCH`, `DELETE` | Получение, обновление, архивация/удаление группы | `api.v1.views.group_detail` |
| `/v1/schedule` | `GET` | Недельная сетка расписания групп по кабинетам и времени | `api.v1.views.schedule_list` |
| `/v1/user/teacher` | `GET`, `POST` | Список учителей / добавление учителя (с привязкой к филиалам) | `api.v1.views_extended.teacher_create_view` |
| `/v1/user/teacher/<id>` | `GET`, `PATCH`, `DELETE` | Карточка учителя, обновление данных/филиалов, удаление (CEO only) | `api.v1.views_extended.teacher_detail_view` |
| `/v1/user/teacher/import` | `POST` | Импорт учителей из Excel/CSV | `api.v1.views_import.teacher_import` |
| `/v1/reports/attendance` | `GET`, `POST` | Просмотр и проставление посещаемости учеников в группе | `api.v1.views_extended.report_attendance` |
| `/v1/reports/teacher-attendance` | `GET`, `POST` | Просмотр и отметка посещаемости учителей по группам | `api.v1.views_extended.report_teacher_attendance` |
| `/v1/salary-settings` | `GET`, `POST` | Настройки формул зарплаты (оклад, процент, за студента) | `api.v1.views_extended.salary_settings` |
| `/v1/finance/payroll` | `GET` | Сводка зарплат: начислено, выплачено, остаток на основе групп и платежей | `api.v1.views_extended.payroll_summary` |
| `/v1/room` | `GET`, `POST` | Список кабинетов и управление ими | `api.v1.views_misc.room_list` |
| `/v1/courses` | `GET`, `POST` | Список учебных курсов | `api.v1.views.course_list` |

---

## 3. Фронтенд Архитектура (Vue 3 + Tailwind + Pinia)

1. **`TeachersView.vue`**:
   - Отображение списка преподавателей, их групп, контактных данных, предметов и филиалов.
   - Модальные окна добавления/редактирования преподавателя.
   - Защита удаления: кнопка удаления скрыта для не-CEO и на собственной карточке.
2. **`GroupsView.vue`**:
   - Главная витрина групп: карточки и табличный вид.
   - Фильтры по филиалу, курсу, учителю, статусу (Активные/Архив).
   - Модалка создания/редактирования группы: выбор курса, преподавателя, кабинета, дней недели (`mon, wed, fri` или `tue, thu, sat`), времени начала и окончания.
   - Статистика по группе: количество активных учеников, должников, наполняемость кабинета.
3. **`ScheduleDrawer.vue` & `SchedulePanel.vue` + `useSchedule.ts`**:
   - Интерактивная сетка расписания: группировка по кабинетам (`Room`) или дням недели, предотвращение накладок по времени.
4. **`TeacherAttendanceReportsView.vue`**:
   - Журнал выходов преподавателей на занятия в разрезе групп.
5. **`ReportsAttendanceView.vue`**:
   - Матрица посещаемости учеников по выбранной группе за месяц.
6. **`FinanceSalariesView.vue`**:
   - Ведомость расчета зарплат учителей по формулам (`groups_count`, `students_count`, `group_payments`).

---

## 4. Бизнес-правила и ограничения

1. **Многофилиальность и Мультитенантность**:
   - Все запросы строго скоупятся по `company` текущего авторизованного пользователя.
   - Учитель может преподавать в нескольких филиалах одной компании (`TeacherBranch`).
2. **Права доступа (RBAC)**:
   - `CEO`: полный доступ ко всем действиям (включая удаление учителей, групп, зарплат).
   - `ADMIN`: управление группами, расписанием, просмотр учителей, выставление посещаемости. Не может удалять преподавателей.
   - `TEACHER`: доступ только к своим группам, своим ученикам, своему журналу посещаемости. Не видит чужих зарплат и чужих групп.
3. **Целостность данных при удалении**:
   - Студенты никогда не удаляются каскадно при удалении или архивации группы (`group.on_delete = SET_NULL`).
   - При мягком удалении студента он открепляется от группы.
   - Отметки посещаемости запрещены в группах, где студент не числится (`student.group_id == group.id`).
