from __future__ import annotations
from dataclasses import dataclass

@dataclass
class AppError(Exception):
    status_code:int
    code:str
    message:str
    hint:str
    retryable:bool=False
    def payload(self)->dict:return {"detail":{"code":self.code,"message":self.message,"hint":self.hint,"retryable":self.retryable}}

def error_payload(code:str,message:str,hint:str,retryable:bool=False)->dict:
    return {"detail":{"code":code,"message":message,"hint":hint,"retryable":retryable}}
