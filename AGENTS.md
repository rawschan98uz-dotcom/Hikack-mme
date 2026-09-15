# INSTRUCTIONS FOR ALL AI AGENTS & ASSISTANTS (Antigravity, Cursor, Claude, Copilot)

> **CRITICAL RULE FOR THIS REPOSITORY**:  
> Always execute the post-feature synchronization protocol described below after ANY code change.

---

## 1. System Architecture & Dual Environment

* **Workspace / Source Repository**: `c:\Users\user\Desktop\Hijack-lms`
  * All source code edits must be done here.
* **Installed Desktop Application**: `C:\Users\user\AppData\Local\Programs\HiJack-LMS`
  * The user interacts with the app in the browser at `http://127.0.0.1:8000/`.
  * The server is run from the **installed directory** with `--noreload`.
  * If changes are made only in the workspace, the user **will not see them** until synchronized!

---

## 2. Mandatory Post-Feature Protocol (Must be run after EVERY feature or fix)

Whenever you add, modify, or fix any feature in this project, you **MUST** complete the following steps before reporting completion:

### Automated Command:
Run the built-in sync script:
```powershell
powershell -ExecutionPolicy Bypass -File "c:\Users\user\Desktop\Hijack-lms\sync-app.ps1"
```

### Or Manual Steps:
1. **Frontend Rebuild (if frontend files modified):**
   ```powershell
   $env:PATH = "C:\Program Files\nodejs;$env:PATH"
   cd app\frontend
   & "C:\Program Files\nodejs\npm.cmd" run build
   ```
2. **Database Migrations in Workspace:**
   ```powershell
   & "C:\Users\user\AppData\Local\Programs\HiJack-LMS\runtime\python\python.exe" app\backend\manage.py makemigrations
   & "C:\Users\user\AppData\Local\Programs\HiJack-LMS\runtime\python\python.exe" app\backend\manage.py migrate
   ```
3. **Sync Files to Installed Directory:**
   * Copy modified backend modules (`accounts`, `api`, `crm`, `finance`, `operations`, `org`, `config`) to `C:\Users\user\AppData\Local\Programs\HiJack-LMS\app\backend\`.
   * Copy `app\frontend\dist\*` to `C:\Users\user\AppData\Local\Programs\HiJack-LMS\app\frontend\dist\`.
4. **Apply Migrations to Installed App Database:**
   ```powershell
   & "C:\Users\user\AppData\Local\Programs\HiJack-LMS\runtime\python\python.exe" "C:\Users\user\AppData\Local\Programs\HiJack-LMS\app\backend\manage.py" migrate
   ```
5. **Restart the Server (Port 8000):**
   * Stop existing python process running from `HiJack-LMS`.
   * Start fresh server process:
     ```powershell
     $serverCmd = "`"C:\Users\user\AppData\Local\Programs\HiJack-LMS\runtime\python\python.exe`" manage.py runserver 127.0.0.1:8000 --noreload"
     Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
         CommandLine = $serverCmd
         CurrentDirectory = "C:\Users\user\AppData\Local\Programs\HiJack-LMS\app\backend"
     }
     ```
6. **Remind the User:**
   * Always inform the user to press **`Ctrl + F5`** (or `Ctrl + Shift + R`) to drop browser cache.

---

## 3. Business & Security Rules
* **User Deletion**:
  * Users can **NEVER** delete their own account (backend rejects with 400 Bad Request; frontend hides delete button on profile).
  * Only users with role `CEO` (or superuser) are permitted to delete staff or teachers.
  * Delete buttons for staff and teachers are hidden for non-CEO users and hidden on own cards.
