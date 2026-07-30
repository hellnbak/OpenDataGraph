from datetime import datetime
from typing import Iterator

def _dt(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).replace(tzinfo=None) if value else None

def scan_drive(credentials_file:str, impersonate_user:str|None=None, drive_id:str|None=None, max_files:int=500)->Iterator[dict]:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install Google connector dependencies from requirements.txt") from exc
    scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"]
    creds=service_account.Credentials.from_service_account_file(credentials_file,scopes=scopes)
    if impersonate_user: creds=creds.with_subject(impersonate_user)
    service=build("drive","v3",credentials=creds,cache_discovery=False)
    token=None; seen=0
    while True:
        params=dict(pageSize=min(1000,max_files-seen),pageToken=token,q="trashed = false",fields="nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime,owners,permissions,parents,driveId,webViewLink,description,properties)",supportsAllDrives=True,includeItemsFromAllDrives=True)
        if drive_id: params.update(corpora="drive",driveId=drive_id)
        result=service.files().list(**params).execute()
        for f in result.get("files",[]):
            owners=','.join(o.get('emailAddress') or o.get('displayName','unknown') for o in f.get('owners',[])) or 'unknown'
            perms=f.get('permissions',[]); public=any(p.get('type')=='anyone' for p in perms)
            yield {"source":"google-drive","source_account":f.get('driveId') or impersonate_user or 'my-drive',"external_id":f"gdrive://{f['id']}","name":f['name'],"path":f.get('webViewLink') or f"gdrive://{f['id']}","size_bytes":int(f.get('size',0)),"mime_type":f.get('mimeType','application/octet-stream'),"created_at":_dt(f.get('createdTime')),"modified_at":_dt(f.get('modifiedTime')),"last_accessed_at":None,"owner":owners,"encryption":"Google-managed","public_access":public,"metadata":{"parents":f.get('parents',[]),"permissions":len(perms),"description":f.get('description',''),"properties":f.get('properties',{})}}
            seen+=1
            if seen>=max_files:return
        token=result.get('nextPageToken')
        if not token:return
