# The Newsroom – Django news application

Readers view articles from publishers and independent journalists;
journalists write articles and newsletters; editors create publishers and
review/approve articles. Includes a REST API with token authentication,
MariaDB as the database, and an automated test suite.

Design, requirements, database design and UI planning are in
[DESIGN.md](DESIGN.md).

**Everything below can be done without the Django admin panel.** Editors
sign up on the site themselves and create publishers on the site.

---

## 1. What you need installed first

| Tool | Why | Check it with |
|---|---|---|
| **Python 3.10 or newer** | runs Django | `python --version` (Mac/Linux: `python3 --version`) |
| **Git** | downloads the project | `git --version` |
| **MariaDB server and client** | the database | see section 3 |

> On Mac/Linux type `python3` wherever this guide says `python`, and `pip3`
> if `pip` is not found.

## 2. Get the project and set up Python

You will use **two kinds of window**, so keep them straight:

* the **terminal** (Command Prompt, PowerShell, Terminal) – where you type
  `git`, `python`, `pip` and `export`/`set` commands; and
* the **MariaDB prompt** (section 3) – where you type SQL such as
  `CREATE DATABASE`. SQL does **not** work in the normal terminal.

### 2.1 Download the project (clone) and go into its folder

Open a terminal in the folder where you keep projects, then:

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
cd YOUR-REPO-NAME
```

(Use the repository link you were given. If you received a zip instead,
unzip it and `cd` into the unzipped folder.)

Confirm you are in the **project root folder** – it is the one that contains
`manage.py`:

```bash
ls            # Windows Command Prompt: dir
```

You should see `manage.py`, `README.md`, `requirements.txt`, `news/` and
`news_project/`. **Stay in this folder for every command below.** If a
command later says `can't open file 'manage.py'` or `No such file ...
requirements.txt`, you are in the wrong folder.

### 2.2 Create and activate a virtual environment (inside the project folder)

```bash
python -m venv .venv
```

This creates a `.venv` folder *inside* the project folder. Activate it:

| System | Command |
|---|---|
| Windows Command Prompt | `.venv\Scripts\activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Mac / Linux | `source .venv/bin/activate` |

When it works, your prompt starts with `(.venv)`.

PowerShell may refuse with "running scripts is disabled". Either use
Command Prompt instead, or run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and retry.

You must activate it again every time you open a new terminal.

### 2.3 Install the Python packages (from the project root, venv active)

```bash
pip install -r requirements.txt
```

This installs Django, Django REST framework, requests and `mysqlclient`
(the MariaDB driver). If `mysqlclient` fails to install, install the client
libraries first and run the command again:

* **Ubuntu/Debian:** `sudo apt install libmariadb-dev pkg-config build-essential`
* **macOS:** `brew install mariadb pkg-config`
* **Windows:** normally no extra step (a ready-made wheel is used).

## 3. Set up the MariaDB database

### 3.1 Install MariaDB (skip if already installed)

* **Windows:** download the installer from <https://mariadb.org/download/>.
  When asked, set a **root password** and write it down. Keep port `3306`
  and "Install as service" ticked.
* **macOS:** `brew install mariadb` then `brew services start mariadb`
* **Ubuntu/Debian:**
  `sudo apt install mariadb-server` then `sudo systemctl start mariadb`

### 3.2 Open the MariaDB prompt (this is where the SQL goes)

Open it in one of these ways:

* **Windows (easiest):** press the Windows key, type **MariaDB**, and open
  **"MySQL Client (MariaDB …)"**. Enter your root password. If you cannot
  find it, also try **HeidiSQL** (installed with MariaDB) – open a session
  and use its *Query* tab to paste the SQL below.
* **Mac:** in a terminal run `mariadb -u root -p` (or `mysql -u root -p`).
* **Linux:** in a terminal run `sudo mariadb`.

You know it worked when the prompt changes to `MariaDB [(none)]>`.
If a terminal says `'mariadb' is not recognized`, MariaDB is either not
installed or its `bin` folder is not on your PATH – use the Start-menu client
above instead.

### 3.3 Run the SQL

At the `MariaDB [(none)]>` prompt paste the following. First change
`choose-a-password` to a password you will remember (letters and numbers
only is safest – no quote marks, `$` or `!`):

```sql
CREATE DATABASE news_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'news_user'@'localhost' IDENTIFIED BY 'choose-a-password';
GRANT ALL PRIVILEGES ON news_db.* TO 'news_user'@'localhost';
GRANT ALL PRIVILEGES ON test_news_db.* TO 'news_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Every line should answer `Query OK`. (`test_news_db` is a temporary database
Django creates when you run the tests, so the user needs permission for it.)

## 4. Tell the project how to connect (environment variables)

These commands are typed in the **normal terminal** (not the MariaDB
prompt), in the **same terminal window** where you will run `python
manage.py ...` with the virtual environment active. They only last for that
window, so **repeat them whenever you open a new terminal**, before running
`migrate`, `test` or `runserver`.

Use the password you chose in section 3.3.

**Windows – Command Prompt**
```
set DB_NAME=news_db
set DB_USER=news_user
set DB_PASSWORD=choose-a-password
```

**Windows – PowerShell**
```
$env:DB_NAME="news_db"
$env:DB_USER="news_user"
$env:DB_PASSWORD="choose-a-password"
```

**Mac / Linux**
```
export DB_NAME=news_db
export DB_USER=news_user
export DB_PASSWORD=choose-a-password
```

Check it took effect (Command Prompt: `echo %DB_USER%`; PowerShell:
`echo $env:DB_USER`; Mac/Linux: `echo $DB_USER`) – it should print `news_user`.

Host and port default to `127.0.0.1` and `3306`; change them only with
`DB_HOST` / `DB_PORT` if your MariaDB is elsewhere.

*Just want to try the site without MariaDB?* Set `DB_ENGINE=sqlite` the
same way instead of the three lines above.

## 5. Create the tables, test, and run

From the project root, with the virtual environment active and the variables
from section 4 set:

```bash
python manage.py migrate
```
Creates all tables **and** the Reader, Editor and Journalist groups with
their permissions. If Django says your models have changes not reflected in
a migration, run `python manage.py makemigrations news` then `migrate` again.

```bash
python manage.py test
```
Runs the automated tests. The last line should say `OK`.

```bash
python manage.py runserver
```
Leave this running and open <http://127.0.0.1:8000/> in your browser. Stop
it with `Ctrl+C`.

## 5A. Run with Docker (alternative to sections 2 to 5)

You do **not** need Python, a virtual environment or MariaDB installed for
this route – only Docker. Install Docker Desktop from
<https://www.docker.com/products/docker-desktop/>, start it, and check:

```bash
docker --version
```

Open a terminal **in the project root folder** (the one containing
`Dockerfile` and `manage.py`).

**Quick run (SQLite inside the container)**

```bash
docker build -t newsroom .
docker run --rm -p 8000:8000 newsroom
```

Open <http://127.0.0.1:8000/>. Stop with `Ctrl+C`. Data lives inside the
container and is lost when it stops. Run the tests in the same image with:

```bash
docker run --rm newsroom python manage.py test
```

**Run with MariaDB (docker compose)**

1. Copy the example settings file and choose **your own** passwords in it.
   The real `.env` file is ignored by Git so secrets are never committed.
   * Windows: `copy .env.example .env`
   * Mac/Linux: `cp .env.example .env`
2. Open `.env` in a text editor and replace the two example passwords.
3. Start everything:
   ```bash
   docker compose up --build
   ```
4. Open <http://127.0.0.1:8000/>. Stop with `Ctrl+C`; remove the containers
   with `docker compose down` (add `-v` to also delete the database data).

**Docker playground (no install):** go to <https://labs.play-with-docker.com/>,
log in, click *Add new instance*, then run
`git clone <repo link>`, `cd <repo folder>`, the two quick-run commands
above, and click the **8000** badge that appears.

### Secrets

No passwords or tokens are stored in this repository. You supply them
yourself: the database password you choose in section 3.3 (virtual
environment route) or in `.env` (Docker route). If you also want to use the
optional `/api/approved/` shared secret, set `APPROVED_API_TOKEN` in your
environment (a development default is used otherwise).

## 5B. Documentation (Sphinx)

HTML documentation generated from the code's docstrings is stored in
`docs/_build/html`. Open `docs/_build/html/index.html` in a browser.

To rebuild it (virtual environment active, from the project root):

```bash
pip install -r docs/requirements.txt
sphinx-build -b html -d docs/_build/doctrees docs docs/_build/html
```

## 6. Using the site (walkthrough – no admin panel needed)

The top bar only shows the pages your role may use. After you log in, the
home page also shows a short "Getting started" box for your role.

Use a **private/incognito window** for each extra user so you can stay
logged in as several people at once.

1. **Register an editor.** Go to <http://127.0.0.1:8000/register/>, enter a
   username (e.g. `editor1`), email and password, choose **Editor** as the
   role and submit. You are logged in automatically.
2. **Create a publisher.** Click **Publishers → New publisher**, give it a
   name (e.g. "Daily Planet") and save. You become one of its editors
   automatically. (Journalists can be ticked now or added later.)
3. **Register a journalist** (private window): `/register/` with role
   **Journalist** (e.g. `jane`).
4. **Attach the journalist to the publisher.** Back as the editor, open
   **Publishers → Edit** on your publisher, tick `jane` under *Journalists*
   and save. (A journalist can only write for publishers they are listed
   under; with none, their articles are *independent*.)
5. **Register a reader** (another private window): role **Reader**
   (e.g. `sam`). Click **Subscriptions**, tick the publisher and/or Jane, and
   save.
6. **Write an article as the journalist.** Click **Write**, fill in the
   form, choose the publisher (or leave "Independent") and submit. It is
   *awaiting review*: readers cannot see it yet. Track it under **My
   articles**.
7. **Approve it as the editor.** Open **Review queue** and click
   **Approve & publish**. This triggers the signal in `news/signals.py`:
   * an email to the readers subscribed to the journalist/publisher is
     printed in the terminal running `runserver` (console email backend);
   * the article is POSTed to the project's own `/api/approved/` endpoint
     and logged in the database.
8. **Check as the reader.** The article now appears on the home page
   (use **My subscriptions** to see only followed sources).
9. **Newsletters.** As the journalist, click **New newsletter**, tick
   approved articles and save. Readers see it under **Newsletters**;
   editors and the owner can edit or delete it.

Optional: `python manage.py createsuperuser` creates an account for the
admin panel at `/admin/` (for inspecting the *Approved article logs*). It is
not needed for anything above.

## 7. REST API

Get a token, then send it in an `Authorization: Token <token>` header.
(On Windows Command Prompt/PowerShell use `curl.exe`, and put JSON in double
quotes with the inner quotes escaped, or use Postman.)

```bash
# 1. Get a token
curl -X POST http://127.0.0.1:8000/api/token/ -d "username=sam&password=YOUR_PASSWORD"
# {"token": "abc123..."}

# 2. Approved articles / only the reader's subscriptions
curl -H "Authorization: Token abc123..." http://127.0.0.1:8000/api/articles/
curl -H "Authorization: Token abc123..." http://127.0.0.1:8000/api/articles/subscribed/

# 3. Journalist creates an article
curl -X POST http://127.0.0.1:8000/api/articles/ \
     -H "Authorization: Token <journalist token>" \
     -H "Content-Type: application/json" \
     -d '{"title": "Hello", "content": "World"}'

# 4. Editor approves it (fires the email + /api/approved/ POST)
curl -X PATCH http://127.0.0.1:8000/api/articles/1/ \
     -H "Authorization: Token <editor token>" \
     -H "Content-Type: application/json" \
     -d '{"approved": true}'
```

Other endpoints: `GET/PUT/PATCH/DELETE /api/articles/<id>/`,
`/api/newsletters/`, `/api/publishers/` (read-only), `/api/users/me/`,
`/api/login/` (alias of `/api/token/`). Role rules: only journalists POST,
only editors approve, readers can only view. Full tables are in
[DESIGN.md](DESIGN.md#6-routes).

## 8. Tests

```bash
python manage.py test
```

They mock `requests.post` and use Django's in-memory mail outbox, so no
network or mail server is needed. They cover authenticated access per role,
readers only retrieving subscribed content, journalists creating articles,
editors approving/deleting, newsletters, publisher management, sign-up and
the approval signal (successful and failing requests).

## 9. Configuration (environment variables, all optional except DB_PASSWORD)

| Variable | Default | Purpose |
|---|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | `news_db`, `news_user`, empty, `127.0.0.1`, `3306` | MariaDB connection |
| `DB_ENGINE` | `mariadb` | `sqlite` for a quick run without MariaDB |
| `DJANGO_SECRET_KEY` | insecure dev key | change in production |
| `DJANGO_DEBUG` | `1` | set `0` in production |
| `DJANGO_ALLOWED_HOSTS` | empty | comma-separated hosts |
| `DJANGO_EMAIL_BACKEND` | console | e.g. SMTP backend for real mail |
| `SITE_URL` | `http://127.0.0.1:8000` | links in emails, default approval URL |
| `APPROVED_API_URL` | `<SITE_URL>/api/approved/` | where approvals are POSTed (empty disables) |
| `APPROVED_API_TOKEN` | dev token | shared secret for `/api/approved/` |

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `can't open file 'manage.py'` / `requirements.txt not found` | You are not in the project root folder. `cd` into the folder containing `manage.py`. |
| `No module named django` | The virtual environment is not active – run the activate command from 2.2. |
| `Access denied for user 'news_user'` | Password differs from section 3.3, or the variables were not set in *this* terminal window. |
| `Can't connect to MySQL server` | MariaDB is not running – start it (section 3.1). |
| `Unknown database 'news_db'` | The SQL in 3.3 was not run (or ran in the wrong place). |
| Tests: `Access denied ... test_news_db` | The second `GRANT` in 3.3 is missing – run it again. |
| `'mariadb' is not recognized` | Use the Start-menu "MySQL Client (MariaDB)" or HeidiSQL (3.2). |
| Port 8000 busy | `python manage.py runserver 8001` and use that port in the URLs. |

## 11. Code style and layout

PEP 8 (checked with `flake8 --max-line-length=79`), docstrings throughout,
small single-purpose functions, form/serializer validation of user input,
and external failures (email/HTTP) logged rather than raised.

```
news_project/        project settings and root URLs
news/models.py       CustomUser, Publisher, Article, Newsletter, ApprovedArticleLog
news/groups.py       role groups and their permissions
news/signals.py      approval signal, subscription clean-up, group creation
news/services.py     email and POST side effects
news/queries.py      shared article queries
news/permissions.py  role checks (web + API)
news/views.py        HTML views          news/api_views.py  REST views
news/serializers.py  DRF serializers     news/forms.py      forms
news/templates/      HTML templates
news/tests/          automated tests
docs/                Sphinx source (.rst, conf.py) and generated HTML
Dockerfile           container image;  docker-compose.yml  app + MariaDB
```
