export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export type ErrorDetail={code:string;message:string;hint:string;retryable:boolean};
export class ApiError extends Error{code:string;hint:string;retryable:boolean;status:number;constructor(detail:ErrorDetail,status:number){super(detail.message);this.name="ApiError";this.code=detail.code;this.hint=detail.hint;this.retryable=detail.retryable;this.status=status}}
function announce(error:ApiError){if(typeof window!=="undefined")window.dispatchEvent(new CustomEvent("fourth-down-error",{detail:{code:error.code,message:error.message,hint:error.hint,retryable:error.retryable}}))}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response:Response;
  try{response=await fetch(`${API}${path}`,{...init,headers:{"Content-Type":"application/json",...init?.headers},cache:"no-store"})}
  catch{const error=new ApiError({code:"ENGINE_OFFLINE",message:"Fourth Down is not running.",hint:"Keep both server windows open, or restart Start Fourth Down.bat and try again.",retryable:true},0);announce(error);throw error}
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    const raw=body?.detail;
    const detail:ErrorDetail=typeof raw==="object"&&raw?.message?raw:{code:`HTTP_${response.status}`,message:typeof raw==="string"?raw:"The engine could not complete that request.",hint:response.status>=500?"Wait a moment and retry. If it continues, restart Fourth Down.":"Review your information and try again.",retryable:response.status>=500};
    const error=new ApiError(detail,response.status);announce(error);throw error
  }
  return response.json() as Promise<T>;
}
