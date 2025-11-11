from pydantic import BaseModel
from typing import TypeVar, Generic, Optional

# Define a TypeVar for the generic data payload
DataT = TypeVar("DataT")


class PaginationMeta(BaseModel):
    """
    Metadata structure used in the standardized APIResponse,
    now including all required fields per specification.
    """

    total: int
    limit: int = 1  # Defaulting to 1 for non-paginated endpoints
    page: int = 1  # Defaulting to 1
    total_pages: int = 1  # Defaulting to 1
    has_next: bool = False
    has_previous: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "total": 1,
                "limit": 10,
                "page": 1,
                "total_pages": 1,
                "has_next": False,
                "has_previous": False,
            }
        }


class APIResponse(BaseModel, Generic[DataT]):
    """
    Standardized API response structure (R1.4).
    This wrapper ensures consistency across all successful responses.
    """

    success: bool = True
    message: str
    data: DataT
    meta: Optional[PaginationMeta] = None

    class Config:
        # Pydantic configuration to allow the generic type
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation successful.",
                "data": {"key": "value"},
                "meta": {"total": 1},
            }
        }
