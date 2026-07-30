from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:int; source:str; source_account:str; external_id:str; name:str; path:str; mime_type:str; size_bytes:int; owner:str; business_domain:str; sensitivity:str; classification_labels:str; classification_reason:str; classification_confidence:float; created_at:datetime|None; modified_at:datetime|None; last_accessed_at:datetime|None; first_seen_at:datetime; last_seen_at:datetime; age_days:int; stale_score:int; lifecycle_state:str; retention_action:str; retention_reason:str; public_access:bool; encryption:str; ai_access:str; ai_access_reason:str

class AgentOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int; key:str; name:str; owner:str; business_purpose:str; framework:str; models:str; allowed_domains:str; max_sensitivity:str; allowed_destinations:str; approval_status:str; risk_level:str; last_activity_at:datetime|None

class AgentCreate(BaseModel):
    key:str; name:str; owner:str; business_purpose:str; framework:str="custom"; models:str=""; allowed_domains:str=""; max_sensitivity:str="Internal"; allowed_destinations:str="internal-rag,private-model"; approval_status:str="Approved"; risk_level:str="Medium"

class PolicyRequest(BaseModel):
    asset_id:int
    destination:str=Field(default="external-ai")
    action:str=Field(default="send")
    agent_key:str="customer-support-copilot"
    purpose:str="summarization"
    destination_region:str="us"

class PolicyDecision(BaseModel):
    decision:str; asset_id:int; agent_key:str; destination:str; action:str; purpose:str; risk_score:int; reasons:list[str]; controls:list[str]; confidence:float; policy_version:str; expires_in_seconds:int

class S3ScanRequest(BaseModel):
    bucket:str; prefix:str=""; region:str|None=None; max_objects:int=Field(default=500,ge=1,le=5000)

class GDriveScanRequest(BaseModel):
    credentials_file:str="credentials.json"; impersonate_user:str|None=None; drive_id:str|None=None; max_files:int=Field(default=500,ge=1,le=5000)

class DemoGenerateRequest(BaseModel):
    profile:str="financial-services"; samples:int=Field(default=240,ge=80,le=600); seed:int=Field(default=41,ge=0,le=999999)
