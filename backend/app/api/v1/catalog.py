"""Router para el catálogo de precios de productos y servicios."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.catalog import (
    CatalogImportResult,
    CatalogItemCreate,
    CatalogItemOut,
    CatalogItemUpdate,
    CatalogPage,
)
from app.services import catalog as catalog_service

router = APIRouter()


@router.get("", response_model=CatalogPage)
async def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=100),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CatalogPage:
    """Lista los ítems del catálogo para el tenant autenticado."""
    return await catalog_service.list_catalog(
        db=db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit,
        search=search,
        active_only=active_only,
    )


@router.post("", response_model=CatalogItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: CatalogItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CatalogItemOut:
    """Crea un nuevo ítem en el catálogo."""
    item = await catalog_service.create_catalog_item(
        db=db,
        tenant_id=current_user.tenant_id,
        data=body,
    )
    return CatalogItemOut.model_validate(item)


@router.get("/{item_id}", response_model=CatalogItemOut)
async def get_item(
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CatalogItemOut:
    """Obtiene un ítem específico del catálogo."""
    item = await catalog_service.get_catalog_item(
        db=db,
        tenant_id=current_user.tenant_id,
        item_id=item_id,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ítem no encontrado en el catálogo",
        )
    return CatalogItemOut.model_validate(item)


@router.put("/{item_id}", response_model=CatalogItemOut)
async def update_item(
    item_id: UUID,
    body: CatalogItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CatalogItemOut:
    """Actualiza un ítem del catálogo."""
    item = await catalog_service.get_catalog_item(
        db=db,
        tenant_id=current_user.tenant_id,
        item_id=item_id,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ítem no encontrado en el catálogo",
        )
    updated = await catalog_service.update_catalog_item(
        db=db,
        item=item,
        data=body,
    )
    return CatalogItemOut.model_validate(updated)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Desactiva un ítem del catálogo (soft-delete)."""
    item = await catalog_service.get_catalog_item(
        db=db,
        tenant_id=current_user.tenant_id,
        item_id=item_id,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ítem no encontrado en el catálogo",
        )
    await catalog_service.deactivate_catalog_item(db=db, item=item)


@router.post("/import-csv", response_model=CatalogImportResult)
async def import_csv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CatalogImportResult:
    """Carga masiva de ítems del catálogo mediante archivo CSV."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener formato .csv",
        )

    content = await file.read()
    return await catalog_service.import_catalog_csv(
        db=db,
        tenant_id=current_user.tenant_id,
        csv_bytes=content,
    )
