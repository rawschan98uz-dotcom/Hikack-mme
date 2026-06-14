# modme_clone — Community Reference (Django)

Source: https://github.com/akhroruz/modme_clone (MIT, unofficial)

## Stack

- Python / Django
- Django REST Framework
- PostgreSQL
- Elasticsearch (search)
- pytest for tests

## App Structure

```
apps/
  groups/     # branches, courses, rooms, holidays, groups
  users/      # students, staff, leads, archive
  crm/        # CRM features
  payments/   # payment logic
```

## API Prefix

```
/api/v1/
```

Swagger UI at root `/`.

## Useful for Clone

This repo mirrors ModMe domain concepts:
- `Branch`, `Company`, `Course`, `Group`, `Room`, `Holiday`
- `User` roles, `Lead`, student archive
- Payment modules
- Excel export utilities

**Note**: This is a learning project (2023), not feature-complete vs production ModMe.

## Running (from upstream README)

```bash
make test    # pytest with coverage
make mig     # migrations
make admin   # create superuser
make load    # load fixtures
```
