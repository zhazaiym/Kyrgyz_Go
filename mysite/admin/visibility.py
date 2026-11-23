"""The "show on the site" switch in panel lists: one click, saved at once, no page reload."""

from markupsafe import Markup
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from mysite.database.db import SessionLocal
from mysite.database.models import Admin
from mysite.database.social_models import AuthProvider

# Here is_active is not about the site: an administrator's access, and a sign-in
# provider that is switched on only after its keys are checked in the form.
NOT_ON_SITE = (Admin, AuthProvider)


def shown_on_site(view):
    return hasattr(view.model, 'is_active') and view.model not in NOT_ON_SITE


def switch(model, _attribute):
    return Markup(
        '<input type="checkbox" class="form-check-input kt-visibility" role="switch"'
        ' aria-label="Показывать на сайте" data-pk="{}"{}>'
    ).format(model.id, Markup(' checked') if model.is_active else '')


def add_switch(view):
    """Show the switch as a list column; the detail page keeps plain text."""
    if 'is_active' not in [getattr(column, 'key', column) for column in view.column_list]:
        view.column_list = [*view.column_list, view.model.is_active]
    view.column_formatters = {**view.column_formatters, 'is_active': switch}


def visibility_endpoint(admin):
    async def change_visibility(request: Request):
        view = next(
            (
                view
                for view in admin.views
                if getattr(view, 'identity', None) == request.path_params['identity']
                and shown_on_site(view)
            ),
            None,
        )
        if view is None:
            return JSONResponse({'detail': 'not_found'}, status_code=404)
        if not await admin.authentication_backend.authenticate(request) or not (
            await run_in_threadpool(view.is_accessible, request)
        ):
            return JSONResponse({'detail': 'forbidden'}, status_code=403)
        try:
            identity = int(request.path_params['pk'])
            shown = (await request.json())['is_active']
        except (ValueError, KeyError, TypeError):
            return JSONResponse({'detail': 'invalid_request'}, status_code=400)
        if not isinstance(shown, bool):
            return JSONResponse({'detail': 'invalid_request'}, status_code=400)

        def save():
            with SessionLocal() as db:
                record = db.get(view.model, identity)
                if record is None:
                    return None
                record.is_active = shown
                db.commit()
                return record.is_active

        saved = await run_in_threadpool(save)
        if saved is None:
            return JSONResponse({'detail': 'not_found'}, status_code=404)
        return JSONResponse({'is_active': saved})

    return change_visibility
