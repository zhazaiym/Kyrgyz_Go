from fastapi import Query


class Pagination:
    def __init__(
        self,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        self.limit = limit
        self.offset = offset


def filtered_list(db, model, filters, pagination, active_only=False):
    query = db.query(model)

    if active_only:
        query = query.filter(model.is_active.is_(True))

    query = filters.filter(query)
    query = filters.sort(query)
    query = query.order_by(model.id.asc())

    return (
        query
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )