from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import Client
from api.db.session import get_db
from api.listing import ListParams, paginate
from api.schemas import ClientIn, ClientOut
from api.security import Principal, current_principal

router = APIRouter(prefix="/v1/clients", tags=["clients"])
SORTABLE = {"name": Client.name, "created_at": Client.created_at}


def owned_client(db: Session, principal: Principal, client_id: UUID) -> Client:
    client = db.scalar(
        select(Client).where(Client.id == client_id, Client.user_id == principal.user_id)
    )
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


@router.get("")
def list_clients(
    response: Response,
    params: ListParams = Depends(),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[ClientOut]:
    query = select(Client).where(Client.user_id == principal.user_id)
    rows = paginate(db, query, params, SORTABLE, "created_at", response)
    return [ClientOut.model_validate(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    body: ClientIn, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> ClientOut:
    client = Client(
        user_id=principal.user_id, name=body.name, email=body.email.lower(), country=body.country
    )
    db.add(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already have a client with this email"
        ) from None
    return ClientOut.model_validate(client)


@router.get("/{client_id}")
def get_client(
    client_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> ClientOut:
    return ClientOut.model_validate(owned_client(db, principal, client_id))
