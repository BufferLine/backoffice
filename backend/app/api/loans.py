import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.services.file_storage import FileStorageService, get_file_storage
from app.schemas.loan import (
    AllocationItem,
    LoanBalanceResponse,
    LoanCreate,
    LoanListResponse,
    LoanResponse,
    LoanUpdate,
)
from app.services import loan as loan_svc

router = APIRouter()


@router.post("", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
async def create_loan(
    data: LoanCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanResponse:
    loan = await loan_svc.create_loan(db, data, current_user.id)
    await db.commit()
    await db.refresh(loan)
    return LoanResponse.model_validate(loan)


@router.get("", response_model=LoanListResponse)
async def list_loans(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    loan_status: Optional[str] = None,
    loan_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> LoanListResponse:
    items, total = await loan_svc.list_loans(
        db, status=loan_status, loan_type=loan_type, page=page, per_page=per_page
    )
    return LoanListResponse(
        items=[LoanResponse.model_validate(l) for l in items],
        total=total,
    )


@router.get("/{loan_id}", response_model=LoanResponse)
async def get_loan(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanResponse:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    return LoanResponse.model_validate(loan)


@router.patch("/{loan_id}", response_model=LoanResponse)
async def update_loan(
    loan_id: uuid.UUID,
    data: LoanUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanResponse:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    try:
        loan = await loan_svc.update_loan(db, loan, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    await db.commit()
    await db.refresh(loan)
    return LoanResponse.model_validate(loan)


@router.get("/{loan_id}/balance", response_model=LoanBalanceResponse)
async def get_loan_balance(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanBalanceResponse:
    try:
        principal, total_allocated, outstanding, allocations = await loan_svc.get_loan_balance(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return LoanBalanceResponse(
        principal=principal,
        total_allocated=total_allocated,
        outstanding=outstanding,
        allocations=[AllocationItem.model_validate(a) for a in allocations],
    )


@router.post("/{loan_id}/mark-repaid", response_model=LoanResponse)
async def mark_repaid(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanResponse:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    try:
        loan = await loan_svc.mark_repaid(db, loan, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    await db.commit()
    await db.refresh(loan)
    return LoanResponse.model_validate(loan)


@router.post("/{loan_id}/write-off", response_model=LoanResponse)
async def write_off_loan(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanResponse:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    loan = await loan_svc.write_off_loan(db, loan, current_user.id)
    await db.commit()
    await db.refresh(loan)
    return LoanResponse.model_validate(loan)


@router.post("/{loan_id}/generate-pdf", response_model=dict)
async def generate_loan_pdf(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> dict:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    try:
        file_id = await loan_svc.generate_loan_agreement_pdf(db, loan, current_user.id, file_storage)
    except ValueError as e:
        msg = str(e)
        if "immutable" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    await db.commit()
    return {"document_file_id": str(file_id)}


@router.post("/{loan_id}/generate-statement", response_model=dict)
async def generate_loan_statement(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> dict:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    try:
        file_id = await loan_svc.generate_loan_statement_pdf(db, loan, current_user.id, file_storage)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.commit()
    return {"document_file_id": str(file_id)}


@router.post("/{loan_id}/generate-discharge", response_model=dict)
async def generate_loan_discharge(
    loan_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("loan:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> dict:
    loan = await loan_svc.get_loan(db, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Loan {loan_id} not found")
    try:
        file_id = await loan_svc.generate_loan_discharge_pdf(db, loan, current_user.id, file_storage)
    except ValueError as e:
        msg = str(e)
        if "Company settings" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    await db.commit()
    return {"document_file_id": str(file_id)}
