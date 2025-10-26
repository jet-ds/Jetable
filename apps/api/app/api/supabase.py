"""
Supabase integration API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import logging
from uuid import uuid4

from app.api.deps import get_db
from app.models.projects import Project
from app.models.project_services import ProjectServiceConnection
from app.services.supabase_service import (
    SupabaseService,
    SupabaseAPIError,
    validate_supabase_token,
    check_project_exists
)
from app.services.token_service import get_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["supabase"])


class SupabaseConnectRequest(BaseModel):
    project_name: str
    project_ref: Optional[str] = None


class SupabaseConnectResponse(BaseModel):
    success: bool
    project_ref: Optional[str] = None
    project_url: Optional[str] = None
    message: str


class SupabaseProject(BaseModel):
    id: str
    name: str
    ref: str
    status: str
    organization_id: str
    organization_name: str
    region: str
    created_at: str


class SupabaseProjectListResponse(BaseModel):
    success: bool
    projects: List[SupabaseProject]


@router.get("/supabase/projects", response_model=SupabaseProjectListResponse)
async def list_supabase_projects(db: Session = Depends(get_db)):
    """List all Supabase projects accessible with the configured token"""

    # Get Supabase token
    supabase_token = get_token(db, "supabase")
    if not supabase_token:
        raise HTTPException(
            status_code=401,
            detail="Supabase token not configured. Please add your Supabase token in Global Settings."
        )

    try:
        # Initialize Supabase service
        supabase_service = SupabaseService(supabase_token)

        # Validate token
        validation = await supabase_service.check_token_validity()
        if not validation.get("valid"):
            raise HTTPException(status_code=401, detail="Invalid Supabase token")

        # List projects
        projects = await supabase_service.list_projects()

        # Format response
        formatted_projects = [
            SupabaseProject(
                id=p.get("id"),
                name=p.get("name"),
                ref=p.get("ref"),
                status=p.get("status", "unknown"),
                organization_id=p.get("organization_id", ""),
                organization_name=p.get("organization_name", ""),
                region=p.get("region", ""),
                created_at=p.get("created_at", "")
            )
            for p in projects
        ]

        return SupabaseProjectListResponse(
            success=True,
            projects=formatted_projects
        )

    except SupabaseAPIError as e:
        logger.error(f"Supabase API error: {e.message}")
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing Supabase projects: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list Supabase projects: {str(e)}")


@router.post("/projects/{project_id}/supabase/connect", response_model=SupabaseConnectResponse)
async def connect_supabase_project(
    project_id: str,
    request: SupabaseConnectRequest,
    db: Session = Depends(get_db)
):
    """Connect a Supabase project to the local project"""

    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get Supabase token
    supabase_token = get_token(db, "supabase")
    if not supabase_token:
        raise HTTPException(
            status_code=401,
            detail="Supabase token not configured. Please add your Supabase token in Global Settings."
        )

    try:
        # Initialize Supabase service
        supabase_service = SupabaseService(supabase_token)

        # Validate token
        validation = await supabase_service.check_token_validity()
        if not validation.get("valid"):
            raise HTTPException(status_code=401, detail="Invalid Supabase token")

        # If project_ref is provided, use it. Otherwise, find by name
        project_ref = request.project_ref

        if not project_ref:
            # Find project by name
            projects = await supabase_service.list_projects()
            matching_projects = [p for p in projects if p.get("name") == request.project_name]

            if not matching_projects:
                raise HTTPException(
                    status_code=404,
                    detail=f"Supabase project '{request.project_name}' not found"
                )

            if len(matching_projects) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Multiple Supabase projects found with name '{request.project_name}'. Please specify project_ref."
                )

            project_ref = matching_projects[0].get("ref")

        # Get project details
        project_details = await supabase_service.get_project_details(project_ref)

        # Get API keys
        try:
            api_keys = await supabase_service.get_project_api_keys(project_ref)
        except Exception as e:
            logger.warning(f"Could not fetch API keys: {e}")
            api_keys = []

        # Build project URL
        project_url = f"https://supabase.com/dashboard/project/{project_ref}"

        # Save service connection to database
        try:
            # Check if Supabase connection already exists
            existing_connection = db.query(ProjectServiceConnection).filter(
                ProjectServiceConnection.project_id == project_id,
                ProjectServiceConnection.provider == "supabase"
            ).first()

            service_data = {
                "project_ref": project_ref,
                "project_name": project_details.get("name"),
                "project_id": project_details.get("id"),
                "project_url": project_url,
                "database_host": project_details.get("database", {}).get("host"),
                "database_version": project_details.get("database", {}).get("version"),
                "region": project_details.get("region"),
                "status": project_details.get("status"),
                "organization_id": project_details.get("organization_id"),
                "created_at": project_details.get("created_at")
            }

            # Add API keys if available
            if api_keys:
                service_data["has_api_keys"] = True
                # Don't store actual keys in service_data for security
            else:
                service_data["has_api_keys"] = False

            if existing_connection:
                # Update existing connection
                existing_connection.service_data = service_data
                existing_connection.status = "connected"
                db.commit()
                logger.info(f"Updated Supabase connection for project {project_id}")
            else:
                # Create new connection
                connection = ProjectServiceConnection(
                    id=str(uuid4()),
                    project_id=project_id,
                    provider="supabase",
                    status="connected",
                    service_data=service_data
                )
                db.add(connection)
                db.commit()
                logger.info(f"Created new Supabase connection for project {project_id}")

        except Exception as db_error:
            logger.error(f"Database update failed: {db_error}")
            # Don't fail the operation for database issues
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save Supabase connection: {str(db_error)}"
            )

        return SupabaseConnectResponse(
            success=True,
            project_ref=project_ref,
            project_url=project_url,
            message=f"Supabase project '{request.project_name}' connected successfully!"
        )

    except SupabaseAPIError as e:
        logger.error(f"Supabase API error: {e.message}")
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Supabase connection: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect Supabase project: {str(e)}")


@router.get("/projects/{project_id}/supabase/status")
async def get_supabase_connection_status(project_id: str, db: Session = Depends(get_db)):
    """Get Supabase connection status for a project"""

    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Supabase token exists
    supabase_token = get_token(db, "supabase")
    token_exists = bool(supabase_token)

    # Get Supabase connection
    connection = db.query(ProjectServiceConnection).filter(
        ProjectServiceConnection.project_id == project_id,
        ProjectServiceConnection.provider == "supabase"
    ).first()

    # Check if project is actually connected
    project_connected = bool(
        connection and
        connection.status == "connected" and
        connection.service_data and
        connection.service_data.get("project_ref")
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "token_exists": token_exists,
            "project_connected": False
        }

    return {
        "connected": project_connected and token_exists,
        "status": connection.status,
        "service_data": connection.service_data or {},
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat() if connection.updated_at else None,
        "token_exists": token_exists,
        "project_connected": project_connected
    }


@router.delete("/projects/{project_id}/supabase/disconnect")
async def disconnect_supabase_project(project_id: str, db: Session = Depends(get_db)):
    """Disconnect Supabase project from our project (does not delete the Supabase project)"""

    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Find Supabase connection
    connection = db.query(ProjectServiceConnection).filter(
        ProjectServiceConnection.project_id == project_id,
        ProjectServiceConnection.provider == "supabase"
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Supabase connection not found")

    # Remove the connection
    db.delete(connection)
    db.commit()

    return {"message": "Supabase project disconnected successfully"}
