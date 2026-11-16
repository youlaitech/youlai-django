<div align="center">

# <img alt="youlai-django" width="40" height="40" src="./docs/images/logo/logo.png" valign="middle"> youlai-django

**Python 3.12 + Django 6.0 Enterprise-Grade Permission Management Backend**

<br>

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20?logo=django)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?logo=apache)](LICENSE)
[![Gitee Star](https://gitee.com/youlaiorg/youlai-django/badge/star.svg)](https://gitee.com/youlaiorg/youlai-django/stargazers)
[![GitHub Star](https://img.shields.io/github/stars/youlaitech/youlai-django?style=social)](https://github.com/youlaitech/youlai-django)

</div>

<p align="center"><img src="./docs/images/rainbow.png" alt="rainbow"></p>

<div align="center">

[![Live Demo](https://img.shields.io/badge/Live%20Demo-2D8CF0?style=for-the-badge\&logo=google-chrome\&logoColor=white)](https://admin.youlai.tech)
[![Mobile Demo](https://img.shields.io/badge/Mobile%20Demo-19BE6B?style=for-the-badge\&logo=android\&logoColor=white)](https://app.youlai.tech)
[![Documentation](https://img.shields.io/badge/Documentation-8B5CF6?style=for-the-badge\&logo=gitbook\&logoColor=white)](https://www.youlai.tech/docs/server/spring-boot/)
[![简体中文](https://img.shields.io/badge/简体中文-00B4D8?style=for-the-badge\&logo=google-translate\&logoColor=white)](./README.md)

</div>

## Introduction



**youlai-django** is an enterprise-grade permission management backend built on Django / DRF. It ships with the frontend [vue3-element-admin](https://gitee.com/youlaiorg/vue3-element-admin) and the mobile app [youlai-app](https://gitee.com/youlaiorg/youlai-app), and is one of **7 language implementations** (Java / Node.js / Go / Python / PHP / C# / Rust) that share the same API specification and database schema. It is suitable for learning, reference, and secondary development of enterprise admin systems.



## Core Features



- 🔐 **Security** — JWT + Redis Token dual-session model, token renewal, multi-device mutual exclusion

- 🛡️ **Fine-grained permissions** — RBAC model governing menus, buttons, and APIs in one place

- ⚡ **Code generator** — one-click generation of full-stack CRUD code

- 📦 **Complete modules** — users, roles, menus, departments, dictionaries, files, message center, operation logs

- 🔌 **Real-time communication** — WebSocket push: online user count, dictionary sync, notification broadcast



## System Preview



**PC**



<table align="center">

  <tr>

    <td><img alt="PC Preview 1" width="400" src="./docs/images/preview/pc-01.png"></td>

    <td><img alt="PC Preview 2" width="400" src="./docs/images/preview/pc-02.png"></td>

  </tr>

  <tr>

    <td><img alt="PC Preview 3" width="400" src="./docs/images/preview/pc-03.png"></td>

    <td><img alt="PC Preview 4" width="400" src="./docs/images/preview/pc-04.png"></td>

  </tr>

  <tr>

    <td><img alt="PC Preview 5" width="400" src="./docs/images/preview/pc-05.png"></td>

    <td><img alt="PC Preview 6" width="400" src="./docs/images/preview/pc-06.png"></td>

  </tr>

</table>



**Mobile**



<table align="center">

  <tr>

    <td><img alt="App Preview 1" width="200" src="./docs/images/preview/app-01.png"></td>

    <td><img alt="App Preview 2" width="200" src="./docs/images/preview/app-02.png"></td>

    <td><img alt="App Preview 3" width="200" src="./docs/images/preview/app-03.png"></td>

    <td><img alt="App Preview 4" width="200" src="./docs/images/preview/app-04.png"></td>

  </tr>

</table>



## Quick Start



> Requirements: Python 3.12+ · MySQL 8.0+ · Redis 7.x+



**1. Clone**



```bash

git clone https://gitee.com/youlaiorg/youlai-django.git

cd youlai-django

```



**2. Create a virtual environment**



Windows (PowerShell):

```powershell

python -m venv venv

venv\Scripts\activate

```



macOS / Linux:

```bash

python3 -m venv venv

source venv/bin/activate

```



**3. Install dependencies**



```bash

pip install -r requirements.txt

```



**4. Import database**



Create the business tables and seed data with `sql/mysql/youlai_admin_django.sql` (the dynamic-form extension tables live in `sql/mysql/extensions/dynamic-form.sql`). Then run the following once to create Django's built-in framework tables (auth / contenttypes / sessions / admin); it does not touch business tables. The project keeps no migration files: business schemas always come from the SQL scripts, and after changing models run `python manage.py makemigrations` plus `python manage.py migrate --fake-initial`:



```bash

python manage.py migrate

```

> **PostgreSQL**: `sql/postgresql/` ships the equivalent scripts, generated from the MySQL ones by `youlai-devkit/scripts/gen_pg_from_mysql.py` (**do not edit them by hand**). Set `DB_ENGINE=postgresql` in `.env` (default port 5432) and install `psycopg`; the order is the same: import the SQL first, then run `migrate`. Verify both dialects stay in sync with `python youlai-devkit/scripts/check_sql_parity.py`.

**5. Config file** (optional)



The repository ships with `.env`; adjust the database/Redis connection as needed. The default config works out of the box.



**6. Start the service**



```bash

python manage.py runserver 8000

```



Open http://localhost:8000/api/docs/swagger/ with default credentials `admin` / `123456`.



> See the [Deployment Docs](https://www.youlai.tech/docs/server/django/deploy) for details.



## Tech Stack



| Tech | Version | Description |

|:-----|:--------|:------------|

| Python | 3.12+ | Core language |

| Django | 6.0 | Web framework |

| DRF | 3.16 | REST API |

| SimpleJWT | 5.5 | JWT authentication |

| MySQL | 8.0+ | Database |

| Redis | 7.x | Cache · Session |

| Spectacular | 0.28 | API docs |



## Directory Structure



```

youlai-django/

├── apps/                           # Business apps (modular)

│   ├── auth/                       # Auth module (login/Token/WeChat mini-program)

│   ├── system/                     # Core system module (user/role/menu/dept/dict/notice/log)

│   ├── file/                       # File upload

│   ├── codegen/                    # Code generation

│   └── message/                    # Realtime push

├── config/                         # Project config

│   ├── settings/                   # Environment config (base/dev/prod)

│   ├── urls.py                     # Global routes

│   ├── asgi.py                     # ASGI entry

│   └── wsgi.py                     # WSGI entry

├── core/                           # Shared base capabilities

│   ├── exceptions/                 # Exception handling

│   ├── permissions/                # Permission control

│   ├── middleware/                 # Middleware

│   ├── response.py                 # Unified response format

│   ├── viewsets.py                 # Base viewsets

│   └── pagination.py               # Pagination

├── sql/                            # Database init scripts

├── manage.py                       # Django management entry

└── .env                            # Environment variables

```



## Ecosystem



**Frontend**



| Project | Stack | Description |

|:-----|:------|:------------|

| [vue3-element-admin](https://gitee.com/youlaiorg/vue3-element-admin) | Vue 3 + Element Plus | PC admin frontend (recommended) |

| [youlai-app](https://gitee.com/youlaiorg/youlai-app) | Vue 3 + UniApp | Mobile App |



**Backend**



| Project | Stack | Description |
| [youlai-boot](https://gitee.com/youlaiorg/youlai-boot) | Spring Boot + MyBatis-Plus | Java (recommended) |
| [youlai-nest](https://gitee.com/youlaiorg/youlai-nest) | NestJS + TypeORM | Node.js |
| [youlai-gin](https://gitee.com/youlaiorg/youlai-gin) | Go + Gorm | Go |
| [youlai-django](https://gitee.com/youlaiorg/youlai-django) | Django + DRF | Python |
| [youlai-fastapi](https://gitee.com/youlaiorg/youlai-fastapi) | FastAPI + SQLAlchemy | Python |
| [youlai-think](https://gitee.com/youlaiorg/youlai-think) | ThinkPHP + ThinkORM | PHP |
| [youlai-aspnet](https://gitee.com/youlaiorg/youlai-aspnet) | ASP.NET Core + EF Core | C# |
| [youlai-axum](https://gitee.com/youlaiorg/youlai-axum) | Axum + SeaORM | Rust |
> **youlai-boot** also provides the following variants and branches: [Multi-Tenant](https://gitee.com/youlaiorg/youlai-boot-tenant) · [MyBatis-Flex](https://gitee.com/youlaiorg/youlai-boot-flex) · [Spring Boot 3](https://gitee.com/youlaiorg/youlai-boot/tree/spring-boot-3) · [PostgreSQL](https://gitee.com/youlaiorg/youlai-boot/tree/db-pg) · [Multi-Module](https://gitee.com/youlaiorg/youlai-boot/tree/multi-module)

>

> The eight backends share the same **RESTful API specification** and **database schema**, so the frontend can switch seamlessly.



## Optional Extensions

**AI (off by default)**: enable it and fill the key in `.env`; `config/settings` reads these variables.

```env
AI_ENABLED=true
AI_API_KEY=sk-xxx
```

## Documentation



| Resource | Link |

|:-----|:-----|

| 📖 Full docs site | [www.youlai.tech](https://www.youlai.tech/) |

| 🖥️ PC live preview | [admin.youlai.tech](https://admin.youlai.tech) |

| 📱 Mobile live preview | [app.youlai.tech](https://app.youlai.tech) |

| 🔗 Apifox API docs | [apifox.com](https://www.apifox.cn/apidoc/shared-195e783f-4d85-4235-a038-eec696de4ea5) |

| 🔗 Local API docs | [localhost:8000/api/docs/swagger/](http://localhost:8000/api/docs/swagger/) |



## Contributing



Issues and Pull Requests are welcome! See the [Contribution Guide](https://www.youlai.tech/faq/help).



## License



Released under the [Apache License 2.0](LICENSE); free for commercial use.



---



<table align="center">

  <tr>

    <td align="center">

      <img src="./docs/images/qrcode/wechat-official.jpg" height="180" alt="Official WeChat Account"><br>

      <sub>Official WeChat Account</sub>

    </td>

    <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>

    <td align="center">

      <img src="./docs/images/qrcode/wechat-mp.jpg" height="180" alt="Mini Program"><br>

      <sub>Mini Program</sub>

    </td>

    <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>

    <td align="center">

      <img src="./docs/images/qrcode/wechat-personal.png" height="180" alt="Add author on WeChat"><br>

      <sub>Add author on WeChat</sub>

    </td>

  </tr>

</table>



<p align="center"><em>Technical discussion · Feedback · Business cooperation</em></p>

