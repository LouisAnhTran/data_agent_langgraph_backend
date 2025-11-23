
from typing import Dict, List, Optional, TypedDict


class UploadedAtPayload(TypedDict):
    from_date: str
    to_date: str

class FieldsPayload(TypedDict):
    name: str
    value: str
    
class DocFieldsPayload(TypedDict):
    doctype: str
    fields: List[FieldsPayload]
    
class SearchPayload(TypedDict):
    uploaded_at: Optional[UploadedAtPayload]
    queues: Optional[Dict[str,str]]
    others: DocFieldsPayload