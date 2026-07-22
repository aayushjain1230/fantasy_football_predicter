export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ErrorDetail = {
  code: string;
  message: string;
  hint: string;
  retryable: boolean;
};

export class ApiError extends Error {
  code: string;
  hint: string;
  retryable: boolean;
  status: number;

  constructor(detail: ErrorDetail, status: number) {
    super(detail.message);
    this.name = "ApiError";
    this.code = detail.code;
    this.hint = detail.hint;
    this.retryable = detail.retryable;
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export function normalizeApiError(body: unknown, status: number): ErrorDetail {
  const envelope = isRecord(body) ? body : {};
  const firstDetail = envelope.detail;
  const raw = isRecord(firstDetail) && isRecord(firstDetail.detail)
    ? firstDetail.detail
    : firstDetail;
  const detail = isRecord(raw) ? raw : {};
  const plainDetail = stringValue(raw);

  return {
    code: stringValue(detail.code) ?? `HTTP_${status}`,
    message:
      stringValue(detail.message) ??
      plainDetail ??
      "The engine could not complete that request.",
    hint:
      stringValue(detail.hint) ??
      (status >= 500
        ? "Wait a moment and retry. If it continues, restart Fourth Down."
        : "Review your information and try again."),
    retryable:
      typeof detail.retryable === "boolean" ? detail.retryable : status >= 500,
  };
}

function announce(error: ApiError) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("fourth-down-error", {
        detail: {
          code: error.code,
          message: error.message,
          hint: error.hint,
          retryable: error.retryable,
        },
      }),
    );
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    const error = new ApiError(
      {
        code: "ENGINE_OFFLINE",
        message: "Fourth Down could not reach the decision engine.",
        hint: "Check the backend URL and make sure the backend is running, then try again.",
        retryable: true,
      },
      0,
    );
    announce(error);
    throw error;
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => undefined);
    const error = new ApiError(normalizeApiError(body, response.status), response.status);
    announce(error);
    throw error;
  }

  return response.json() as Promise<T>;
}
