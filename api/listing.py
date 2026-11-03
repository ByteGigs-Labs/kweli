from fastapi import Query, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


class ListParams:
    def __init__(
        self,
        start: int = Query(0, alias="_start", ge=0),
        end: int = Query(25, alias="_end", ge=1),
        sort: str | None = Query(None, alias="_sort", max_length=40),
        order: str = Query("desc", alias="_order", pattern="^(?i)(asc|desc)$"),
    ) -> None:
        self.start = start
        self.limit = max(1, min(end - start, 100))
        self.sort = sort
        self.descending = order.lower() == "desc"


def paginate(
    db: Session, query: Select, params: ListParams, sortable: dict, default: str, response: Response
) -> list:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    column = sortable.get(params.sort or default, sortable[default])
    ordered = query.order_by(column.desc() if params.descending else column.asc())
    response.headers["X-Total-Count"] = str(total)
    return list(db.scalars(ordered.offset(params.start).limit(params.limit)))
