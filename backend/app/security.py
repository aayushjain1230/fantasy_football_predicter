from __future__ import annotations
import os, threading, time
from collections import defaultdict, deque
from urllib.parse import urlparse
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from .errors import error_payload

MAX_BODY_BYTES=int(os.getenv("MAX_REQUEST_BYTES","1048576")); SAFE_METHODS={"GET","HEAD","OPTIONS"}
def allowed_origins()->set[str]: return {x.strip().rstrip("/") for x in os.getenv("ALLOWED_ORIGINS","http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()}
class SlidingWindowLimiter:
    def __init__(self): self.events=defaultdict(deque); self.lock=threading.Lock()
    def allow(self,key:str,limit:int,window:int=60):
        now=time.monotonic()
        with self.lock:
            q=self.events[key]
            while q and q[0]<=now-window:q.popleft()
            if len(q)>=limit:return False,max(1,int(window-(now-q[0])))
            q.append(now);return True,0
LIMITER=SlidingWindowLimiter()
class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request:Request,call_next):
        length=request.headers.get("content-length")
        if length and length.isdigit() and int(length)>MAX_BODY_BYTES:return JSONResponse(error_payload("REQUEST_TOO_LARGE","That request is too large.","Use a smaller input and try again."),413)
        if request.method not in SAFE_METHODS:
            origin=request.headers.get("origin")
            if origin and origin.rstrip("/") not in allowed_origins():return JSONResponse(error_payload("ORIGIN_NOT_ALLOWED","This request came from an untrusted website.","Open Fourth Down from its normal localhost address."),403)
            body=await request.body()
            if len(body)>MAX_BODY_BYTES:return JSONResponse(error_payload("REQUEST_TOO_LARGE","That request is too large.","Use a smaller input and try again."),413)
            async def receive():return {"type":"http.request","body":body,"more_body":False}
            request._receive=receive
        client=request.client.host if request.client else "local"
        if request.url.path.startswith("/api/ask"): bucket,limit="ai",10
        elif request.url.path.startswith(("/api/connect","/api/providers/","/api/digest/","/api/privacy")): bucket,limit="sensitive",12
        else: bucket,limit="general",120
        ok,retry=LIMITER.allow(f"{client}:{bucket}",limit)
        if not ok:return JSONResponse(error_payload("RATE_LIMITED","Fourth Down received too many requests at once.",f"Wait about {retry} seconds, then try again.",True),429,headers={"Retry-After":str(retry)})
        response=await call_next(request)
        for key,value in {"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Cache-Control":"no-store"}.items():response.headers[key]=value
        response.headers["Content-Security-Policy"]="default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response
def validate_discord_webhook(value:str)->str:
    parsed=urlparse(value)
    if parsed.scheme!="https" or parsed.hostname not in {"discord.com","discordapp.com","canary.discord.com","ptb.discord.com"} or not parsed.path.startswith("/api/webhooks/"):raise ValueError("Only an HTTPS Discord webhook URL is allowed")
    return value
def clean_question(value:str)->str:
    if any(ord(c)<32 and c not in "\t\r\n" for c in value):raise ValueError("Question contains unsupported control characters")
    normalized=" ".join(value.split())
    return normalized
