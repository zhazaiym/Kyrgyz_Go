"""Owner-only inspection and revocation; token hashes never appear in forms."""

from uuid import UUID

from fastapi import HTTPException
from sqladmin import ModelView, action
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from mysite.admin.labels import apply_form_rules, apply_labels
from mysite.api.admin_sessions import sql_session_admin
from mysite.database.admin_security_models import AdminSession
from mysite.database.db import SessionLocal
from mysite.database.token_utils import utcnow


class RevocableAdminAccess:
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True

    def is_accessible(self, request):
        with SessionLocal() as db:
            admin = sql_session_admin(db, request.session)
            return bool(admin and admin.role == 'owner')

    def is_visible(self, request):
        return self.is_accessible(request)

    @action(name='revoke', label='Отозвать', confirmation_message='Отозвать выбранный доступ?')
    async def revoke(self, request):
        if not self.is_accessible(request):
            raise HTTPException(403, detail='forbidden')
        try:
            identities = [
                str(UUID(value))
                for value in request.query_params.get('pks', '').split(',')[:100]
                if value
            ]
        except ValueError:
            raise HTTPException(400, detail='invalid_request') from None

        def update():
            with SessionLocal() as db:
                db.query(self.model).filter(
                    self.model.id.in_(identities), self.model.revoked_at.is_(None)
                ).update({'revoked_at': utcnow()}, synchronize_session=False)
                db.commit()

        await run_in_threadpool(update)
        return RedirectResponse(
            request.url_for('admin:list', identity=self.identity), status_code=303
        )


class AdminSessionAdmin(RevocableAdminAccess, ModelView, model=AdminSession):
    name = 'Сессия администратора'
    name_plural = 'Сессии администраторов'
    icon = 'fa-solid fa-key'
    category = 'Доступ'
    category_icon = 'fa-solid fa-lock'
    column_list = [
        AdminSession.id,
        AdminSession.admin_id,
        AdminSession.user_agent,
        AdminSession.created_at,
        AdminSession.last_used_at,
        AdminSession.expires_at,
        AdminSession.revoked_at,
    ]
    column_details_list = column_list
    column_default_sort = (AdminSession.created_at, True)


apply_labels(AdminSessionAdmin)
apply_form_rules(AdminSessionAdmin)
