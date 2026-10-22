# KYRGYZGO Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing FastAPI backend reproducibly deployable and safe to expose to its frontend without adding product features.

**Architecture:** Keep the existing router/service/model layout. Centralize environment-driven database configuration, use Alembic for schema creation, reuse the existing admin identity for API and SQLAdmin protection, and exercise the application against an isolated temporary SQLite database.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, SQLAdmin, pwdlib, python-jose, LangChain Google GenAI, pytest, HTTPX.

## Global Constraints

- Preserve existing route paths and response shapes unless fixing a confirmed runtime defect.
- Keep catalogue reads, contact creation, travel-request creation, and client chat flows public.
- Require administrator authentication for catalogue writes and private customer data.
- Do not delete, reset, or use `kyrgyzgo.db` for automated tests.
- Do not add frontend, Docker, CI, PostgreSQL, or unrelated refactoring.

---

### Task 1: Isolated test harness and database configuration

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_database_config.py`
- Modify: `mysite/database/db.py`
- Modify: `alembic/env.py`

**Interfaces:**
- Consumes: `DATABASE_URL` environment variable.
- Produces: `DATABASE_URL: str`, `engine`, `SessionLocal`, `Base`, and `get_db()` with SQLite-specific arguments applied only to SQLite URLs.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_database_url_comes_from_environment():
    assert db.DATABASE_URL == os.environ["DATABASE_URL"]

def test_all_mappers_configure():
    configure_mappers()
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python -B -m pytest tests/test_database_config.py -q`

Expected: environment URL assertion fails with the current hard-coded URL.

- [ ] **Step 3: Implement environment-driven engine configuration**

```python
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kyrgyzgo.db")
engine_kwargs = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **engine_kwargs)
```

Change Alembic to import `DATABASE_URL` from `mysite.database.db` and import both `models` and `chat_models` before assigning `target_metadata`.

- [ ] **Step 4: Run the focused tests**

Run: `python -B -m pytest tests/test_database_config.py -q`

Expected: all tests pass.

### Task 2: Complete the country/region schema and migrations

**Files:**
- Modify: `mysite/database/models.py`
- Modify: `mysite/database/schema.py`
- Modify: `main.py`
- Create: `alembic/versions/20261020_0001_initial_schema.py`
- Create: `tests/test_country_region.py`

**Interfaces:**
- Consumes: `Country`, `Region`, `/countries/`, and `/regions/`.
- Produces: nullable `Region.country_id`, bidirectional `Country.regions` / `Region.country`, and registered country routes.

- [ ] **Step 1: Write a failing API test**

```python
def test_country_and_region_round_trip(admin_client):
    country = admin_client.post("/countries/", json={"name": "Кыргызстан"})
    assert country.status_code == 200
    region = admin_client.post("/regions/", json={
        "name": "Чүй", "country_id": country.json()["id"]
    })
    assert region.status_code == 200
    assert region.json()["country_id"] == country.json()["id"]
```

- [ ] **Step 2: Confirm the current contract fails**

Run: `python -B -m pytest tests/test_country_region.py -q`

Expected: `/countries/` is absent or `RegionInputSchema` rejects/loses `country_id`.

- [ ] **Step 3: Implement the missing relationship and API registration**

```python
class Region(Base):
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id"))
    country: Mapped["Country | None"] = relationship(back_populates="regions")

class RegionInputSchema(BaseModel):
    name: str
    image: str | None = None
    country_id: int | None = None
```

Add matching update/output fields, restore `Country.regions`, and include `country_router` in `main.py`.

- [ ] **Step 4: Add an initial Alembic migration**

The migration must create every table represented by `Base.metadata`, including chat and translation tables, with the exact foreign keys and unique constraints from the models. Its downgrade drops those tables in reverse dependency order.

- [ ] **Step 5: Verify schema and migration on an empty temporary database**

Run: `$env:DATABASE_URL='sqlite:///./.tmp_migration_test.db'; python -B -m alembic upgrade head`

Expected: exit 0 and all model tables plus `alembic_version` exist. Remove only `.tmp_migration_test.db` after validating its resolved workspace path.

### Task 3: Protect writes, customer data, and SQLAdmin

**Files:**
- Modify: `mysite/api/admin.py`
- Modify: `mysite/admin/setup.py`
- Modify: `mysite/api/about.py`
- Modify: `mysite/api/about_section.py`
- Modify: `mysite/api/country.py`
- Modify: `mysite/api/district.py`
- Modify: `mysite/api/faq.py`
- Modify: `mysite/api/helicopter_image.py`
- Modify: `mysite/api/helicopter_tour.py`
- Modify: `mysite/api/hotel.py`
- Modify: `mysite/api/hotel_image.py`
- Modify: `mysite/api/region.py`
- Modify: `mysite/api/tour.py`
- Modify: `mysite/api/tour_category.py`
- Modify: `mysite/api/tour_image.py`
- Modify: `mysite/api/tour_program.py`
- Modify: `mysite/api/transport.py`
- Modify: `mysite/api/transport_image.py`
- Modify: `mysite/api/trekking.py`
- Modify: `mysite/api/trekking_image.py`
- Modify: `mysite/api/trekking_program.py`
- Modify: `mysite/api/contact.py`
- Modify: `mysite/api/travel_request.py`
- Create: `tests/test_access_control.py`

**Interfaces:**
- Consumes: `get_current_admin()` and the existing `Admin` password hashes.
- Produces: `current_admin` dependencies on protected handlers and `AdminAuthBackend(AuthenticationBackend)` for SQLAdmin sessions.

- [ ] **Step 1: Write failing authorization tests**

```python
def test_catalogue_write_requires_admin(client):
    response = client.post("/tour-categories/", json={"name": "Private"})
    assert response.status_code == 401

def test_contact_creation_stays_public(client):
    response = client.post("/contacts/", json={"name": "A", "phone": "+996700000000"})
    assert response.status_code == 200

def test_contact_list_requires_admin(client):
    assert client.get("/contacts/").status_code == 401
```

- [ ] **Step 2: Confirm unauthenticated writes currently succeed**

Run: `python -B -m pytest tests/test_access_control.py -q`

Expected: at least catalogue-write and private-list assertions fail.

- [ ] **Step 3: Add the existing admin dependency to protected handlers**

```python
def create_category(
    category: TourCategoryInputSchema,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
```

Apply this pattern to catalogue POST/PUT/DELETE and translation retry handlers. Apply it to contact/travel-request GET/PUT/DELETE handlers while leaving their POST handlers public.

- [ ] **Step 4: Add SQLAdmin session authentication**

```python
class AdminAuthBackend(AuthenticationBackend):
    async def login(self, request):
        form = await request.form()
        with SessionLocal() as db:
            admin = db.query(AdminModel).filter(AdminModel.username == form.get("username")).first()
            if not admin or not admin.is_active or not verify_password(str(form.get("password", "")), admin.hashed_password):
                return False
            request.session["admin_id"] = admin.id
            return True

    async def logout(self, request):
        request.session.clear()
        return True

    async def authenticate(self, request):
        admin_id = request.session.get("admin_id")
        with SessionLocal() as db:
            admin = db.get(AdminModel, admin_id) if admin_id else None
            return bool(admin and admin.is_active)
```

Pass `authentication_backend=AdminAuthBackend(secret_key=SECRET_KEY)` to SQLAdmin.

- [ ] **Step 5: Verify public and authorized behavior**

Run: `python -B -m pytest tests/test_access_control.py -q`

Expected: public reads/submissions pass, anonymous protected requests return 401, and bearer-authenticated admin operations pass.

### Task 4: Reproducible server installation

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `DEPLOY.md`
- Create: `tests/test_deployment_files.py`

**Interfaces:**
- Consumes: imports and environment reads in the application.
- Produces: clean-install dependency list and documented environment/server commands.

- [ ] **Step 1: Write failing deployment-file tests**

```python
def test_required_deployment_files_exist():
    assert Path("requirements.txt").is_file()
    assert Path(".env.example").is_file()
    assert Path("DEPLOY.md").is_file()
```

- [ ] **Step 2: Confirm the files are currently missing**

Run: `python -B -m pytest tests/test_deployment_files.py -q`

Expected: missing-file assertions fail.

- [ ] **Step 3: Add the minimal dependency manifest**

```text
alembic==1.18.5
fastapi==0.141.1
langchain-google-genai==4.4.0
pwdlib[argon2]==0.3.1
python-dotenv==1.0.1
python-jose[cryptography]==3.5.0
python-multipart>=0.0.20,<1
sqladmin==0.29.0
SQLAlchemy==2.0.51
uvicorn[standard]==0.52.1
```

- [ ] **Step 4: Add safe environment and deployment documentation**

`.env.example` lists `SECRET_KEY`, `DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, and `CHAT_ALLOWED_ORIGINS` with non-secret values. `DEPLOY.md` documents virtualenv creation, dependency installation, Alembic upgrade/stamp rules, administrator creation, and `uvicorn main:app --host 0.0.0.0 --port 8000`.

Add `venv/`, test databases, and caches to `.gitignore` without removing existing entries.

- [ ] **Step 5: Verify dependency metadata**

Run: `python -B -m pytest tests/test_deployment_files.py -q`

Expected: all deployment-file assertions pass.

### Task 5: End-to-end release verification

**Files:**
- Create: `tests/test_api_smoke.py`
- Create: `tests/test_chat_auth.py`
- Create: `tests/test_ai_config.py`

**Interfaces:**
- Consumes: complete FastAPI application and temporary database fixture.
- Produces: regression coverage for the server contract.

- [ ] **Step 1: Test all non-parameterized GET routes**

Assert `200` for public routes and `401` for protected routes. Assert `/openapi.json` contains every router registered in `main.py`.

- [ ] **Step 2: Test client chat authentication and ownership**

Register two clients, create a session for one, and assert the second receives 404 when requesting its history.

- [ ] **Step 3: Test booking preview and idempotent confirmation without a live AI request**

Build a complete session state directly in the isolated database, confirm it once, then repeat the same revision and assert `already_submitted` with the same request ID.

- [ ] **Step 4: Test AI module configuration without a network call**

Validate that importing both Gemini-backed modules succeeds when
`GEMINI_API_KEY` and model names are configured, and that their configured
models expose the expected invocation interface. Keep live provider calls out
of the deterministic suite.

- [ ] **Step 5: Run the complete suite**

Run: `python -B -m pytest -q`

Expected: zero failures.

- [ ] **Step 6: Run fresh process verification**

Run Uvicorn against an isolated database, request `/`, `/docs`, `/openapi.json`, representative catalogue routes, protected routes, and chat auth routes. Use Postman CLI one-off assertions where supported and report target, behavior, assertion count, and exit code.

- [ ] **Step 7: Verify repository changes**

Run: `git diff --check`

Expected: exit 0 with no whitespace errors. Review `git status --short` and confirm no test database, secret, cache, or virtualenv artifact was added.
