import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, get_current_user, require_permission
from app.database import get_db
from app.models.file import File as FileModel
from app.models.payroll import Employee, PayrollRun
from app.schemas.payroll import (
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    PayrollDeductionResponse,
    PayrollListResponse,
    PayrollMarkPaidRequest,
    PayrollRunCreate,
    PayrollRunResponse,
)
from app.services import payroll as payroll_service
from app.services.audit import AuditService
from app.services.file_storage import FileStorageService, get_file_storage
from app.state_machines import InvalidTransitionError

router = APIRouter()
employees_router = APIRouter()


# ---------------------------------------------------------------------------
# Employee endpoints  (mounted at /api/employees in main.py)
# ---------------------------------------------------------------------------


@employees_router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    employee = await payroll_service.create_employee(
        db, body.model_dump(), created_by=current_user.id
    )
    await db.commit()
    await db.refresh(employee)
    return EmployeeResponse.model_validate(employee)


@employees_router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
) -> list[EmployeeResponse]:
    query = select(Employee).order_by(Employee.name)
    if status_filter is not None:
        query = query.where(Employee.status == status_filter)
    result = await db.execute(query)
    employees = result.scalars().all()
    return [EmployeeResponse.model_validate(e) for e in employees]


@employees_router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return EmployeeResponse.model_validate(employee)


@employees_router.patch("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    employee = await payroll_service.update_employee(
        db, employee_id, body.model_dump(exclude_unset=True)
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await db.commit()
    await db.refresh(employee)
    return EmployeeResponse.model_validate(employee)


# ---------------------------------------------------------------------------
# Payroll run endpoints
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=PayrollRunResponse, status_code=status.HTTP_201_CREATED)
async def create_payroll_run(
    body: PayrollRunCreate,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollRunResponse:
    try:
        run = await payroll_service.create_payroll_run(
            db,
            employee_id=body.employee_id,
            month_str=body.month,
            start_date=body.start_date,
            end_date=body.end_date,
            created_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    await db.commit()
    run = await payroll_service.get_payroll_run(db, run.id)
    return PayrollRunResponse.model_validate(run)


@router.get("/runs", response_model=PayrollListResponse)
async def list_payroll_runs(
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: Optional[str] = Query(None, description="Filter by month YYYY-MM"),
    employee_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> PayrollListResponse:
    runs, total = await payroll_service.list_payroll_runs(
        db,
        month=month,
        employee_id=employee_id,
        status=status_filter,
        page=page,
        per_page=per_page,
    )
    return PayrollListResponse(
        items=[PayrollRunResponse.model_validate(r) for r in runs],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=PayrollRunResponse)
async def get_payroll_run(
    run_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollRunResponse:
    run = await payroll_service.get_payroll_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    return PayrollRunResponse.model_validate(run)


@router.post("/runs/{run_id}/review", response_model=PayrollRunResponse)
async def review_payroll_run(
    run_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollRunResponse:
    try:
        run = await payroll_service.review_payroll(db, run_id, current_user.id)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")

    await db.commit()
    run = await payroll_service.get_payroll_run(db, run_id)
    return PayrollRunResponse.model_validate(run)


@router.post("/runs/{run_id}/finalize", response_model=PayrollRunResponse)
async def finalize_payroll_run(
    run_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:finalize")],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> PayrollRunResponse:
    try:
        run = await payroll_service.finalize_payroll(db, run_id, current_user.id, file_storage)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")

    await db.commit()
    run = await payroll_service.get_payroll_run(db, run_id)
    return PayrollRunResponse.model_validate(run)


@router.post("/runs/{run_id}/mark-paid", response_model=PayrollRunResponse)
async def mark_payroll_paid(
    run_id: uuid.UUID,
    body: PayrollMarkPaidRequest,
    current_user: Annotated[AuthenticatedUser, require_permission("payroll:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollRunResponse:
    try:
        run = await payroll_service.mark_paid(db, run_id, body.payment_id, current_user.id)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")

    await db.commit()
    run = await payroll_service.get_payroll_run(db, run_id)
    return PayrollRunResponse.model_validate(run)


@router.post("/runs/{run_id}/attach-file", response_model=PayrollRunResponse)
async def attach_file_to_payroll_run(
    run_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(require_permission("payroll:write")),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorageService = Depends(get_file_storage),
) -> PayrollRunResponse:
    result = await db.execute(select(PayrollRun).where(PayrollRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")

    storage_key, sha256, size = file_storage.upload(
        file.file, file.filename or "attachment", file.content_type or "application/octet-stream"
    )

    file_record = FileModel(
        storage_key=storage_key,
        original_filename=file.filename,
        mime_type=file.content_type,
        size_bytes=size,
        checksum_sha256=sha256,
        uploaded_by=current_user.id,
        linked_entity_type="payroll_run",
        linked_entity_id=run_id,
    )
    db.add(file_record)
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action="payroll.attach_file",
        entity_type="payroll_run",
        entity_id=run_id,
        actor_id=current_user.id,
        output_data={"file_id": str(file_record.id), "filename": file.filename},
    )

    await db.commit()
    run = await payroll_service.get_payroll_run(db, run_id)
    return PayrollRunResponse.model_validate(run)
