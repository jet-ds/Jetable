"""
Supabase integration service for project connections
"""
import httpx
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

SUPABASE_API_BASE = "https://api.supabase.com"


class SupabaseAPIError(Exception):
    """Custom exception for Supabase API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class SupabaseService:
    """Service class for Supabase API integration"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

    async def check_token_validity(self) -> Dict[str, Any]:
        """Check if the Supabase token is valid by fetching organizations"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{SUPABASE_API_BASE}/v1/organizations",
                    headers=self.headers
                )

                if response.status_code == 200:
                    organizations = response.json()
                    return {
                        "valid": True,
                        "organizations": organizations
                    }
                elif response.status_code == 401:
                    return {"valid": False, "error": "Invalid Supabase token"}
                else:
                    error_text = response.text
                    return {"valid": False, "error": f"API error: {error_text}"}
        except Exception as e:
            logger.error(f"Error checking Supabase token validity: {e}")
            return {"valid": False, "error": str(e)}

    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all Supabase projects accessible with this token"""
        try:
            # First get organizations
            orgs_response = await self.check_token_validity()
            if not orgs_response.get("valid"):
                raise SupabaseAPIError("Invalid token", 401)

            organizations = orgs_response.get("organizations", [])
            all_projects = []

            # Fetch projects for each organization
            async with httpx.AsyncClient() as client:
                for org in organizations:
                    org_id = org.get("id")
                    if not org_id:
                        continue

                    response = await client.get(
                        f"{SUPABASE_API_BASE}/v1/projects",
                        headers=self.headers,
                        params={"organization_id": org_id}
                    )

                    if response.status_code == 200:
                        projects = response.json()
                        for project in projects:
                            project["organization_id"] = org_id
                            project["organization_name"] = org.get("name")
                            all_projects.append(project)

            return all_projects

        except Exception as e:
            logger.error(f"Error listing Supabase projects: {e}")
            raise SupabaseAPIError(f"Error listing projects: {str(e)}")

    async def get_project_details(self, project_ref: str) -> Dict[str, Any]:
        """Get detailed information about a specific Supabase project"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{SUPABASE_API_BASE}/v1/projects/{project_ref}",
                    headers=self.headers
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    raise SupabaseAPIError(f"Project {project_ref} not found", 404)
                else:
                    error_text = response.text
                    raise SupabaseAPIError(f"Failed to get project: {error_text}", response.status_code)

        except SupabaseAPIError:
            raise
        except Exception as e:
            logger.error(f"Error getting Supabase project details: {e}")
            raise SupabaseAPIError(f"Error getting project: {str(e)}")

    async def get_project_api_keys(self, project_ref: str) -> Dict[str, Any]:
        """Get API keys for a Supabase project"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{SUPABASE_API_BASE}/v1/projects/{project_ref}/api-keys",
                    headers=self.headers
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    error_text = response.text
                    raise SupabaseAPIError(f"Failed to get API keys: {error_text}", response.status_code)

        except Exception as e:
            logger.error(f"Error getting Supabase API keys: {e}")
            raise SupabaseAPIError(f"Error getting API keys: {str(e)}")


async def validate_supabase_token(token: str) -> Dict[str, Any]:
    """Validate a Supabase token and return organization info"""
    supabase_service = SupabaseService(token)
    return await supabase_service.check_token_validity()


async def check_project_exists(token: str, project_ref: str) -> bool:
    """Check if a Supabase project exists and is accessible"""
    try:
        supabase_service = SupabaseService(token)
        await supabase_service.get_project_details(project_ref)
        return True
    except SupabaseAPIError as e:
        if e.status_code == 404:
            return False
        raise
