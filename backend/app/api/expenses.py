import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.file import File
from app.schemas.expense import ExpenseCreate, ExpenseListResponse, ExpenseResponse, ExpenseUpdate
from app.services import expense as expense_svc
from app.services.file_storage import get_file_storage
from app.state_machines import InvalidTransitionError

router = APIRouter()


@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    data: ExpenseCreate,
    current_user: Annotated[AuthenticatedUser, require_permission("expense:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpenseResponse:
    expense = await expense_svc.create_expense(db, data, current_user.id)
    return ExpenseResponse.model_validate(expense)


@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    current_user: Annotated[AuthenticatedUser, require_permission("expense:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: Optional[str] = None,
    category: Optional[str] = None,
    expense_status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> ExpenseListResponse:
    items, total = await expense_svc.list_expenses(
        db, month=month, category=category, status=expense_status, page=page, per_page=per_page
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(e) for e in items],
        total=total,
    )


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("expense:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpenseResponse:
    try:
        expense = await expense_svc.get_expense(db, expense_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
    current_user: Annotated[AuthenticatedUser, require_permission("expense:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpenseResponse:
    try:
        expense = await expense_svc.update_expense(db, expense_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return ExpenseResponse.model_validate(expense)


@router.post("/{expense_id}/confirm", response_model=ExpenseResponse)
async def confirm_expense(
    expense_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("expense:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpenseResponse:
    try:
        expense = await expense_svc.confirm_expense(db, expense_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return ExpenseResponse.model_validate(expense)


@router.post("/{expense_id}/reimburse", response_model=ExpenseResponse)
async def reimburse_expense(
    expense_id: uuid.UUID,
    payment_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("expense:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpenseResponse:
    try:
        expense = await expense_svc.reimburse_expense(db, expense_id, payment_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return ExpenseResponse.model_validate(expense)


@router.post("/{expense_id}/attach-file", response_model=dict)
async def attach_file(
    expense_id: uuid.UUID,
    file: UploadFile,
    current_user: Annotated[AuthenticatedUser, require_permission("expense:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        expense = await expense_svc.get_expense(db, expense_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    storage = get_file_storage()
    original_filename = file.filename or "upload"
    mime_type = file.content_type or "application/octet-stream"

    try:
        storage_key, checksum, size = storage.upload(file.file, original_filename, mime_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))

    file_record = File(
        storage_key=storage_key,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size,
        checksum_sha256=checksum,
        uploaded_by=current_user.id,
        linked_entity_type="expense",
        linked_entity_id=expense.id,
    )
    db.add(file_record)
    await db.flush()

    return {"file_id": str(file_record.id), "storage_key": storage_key}
