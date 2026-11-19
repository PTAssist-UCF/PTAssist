/**
 * How the web app talks to the backend API.
 *
 * Every hook that Orval generates in src/api/ (for example useGetMe) sends its request
 * through apiFetch below. apiFetch adds the API's address (VITE_API_URL) and the
 * signed-in user's Clerk token, and turns an error answer into an ApiError, so the
 * hook's `error` is set instead of its `data`.
 *
 * This file is written by hand. src/api/ is generated: never edit it.
 */
import { env } from '@/config/env';

/** An error answer from the API, such as 401 (not signed in) or 403 (wrong role). */
export class ApiError<Body = unknown> extends Error {
  readonly status: number;
  /** The answer's body. FastAPI errors look like { "detail": "..." }. */
  readonly body: Body;

  constructor(status: number, body: Body) {
    super(`The API answered with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/**
 * The error type of every generated hook (Orval uses it): `error.status`, `error.body`.
 * If the API could not be reached at all (server down, offline, CORS), the error is a
 * plain Error with no status, so check `error instanceof ApiError` first.
 */
export type ErrorType<Body> = ApiError<Body>;

/** Returns the signed-in user's Clerk session token, or null when nobody is signed in. */
type TokenGetter = () => Promise<string | null>;

// Until ApiAuth sets Clerk's getter (and in tests that set none), requests go out
// without a token.
let getToken: TokenGetter = async () => null;

/** Called whenever an API request answers 401 (e.g. expired session). */
type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler = () => {};

/** Tells apiFetch what to do on a 401 answer (e.g. redirect to sign-in). */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

/**
 * Tells apiFetch how to get the signed-in user's token. src/components/ApiAuth.tsx calls
 * this with Clerk's getToken, from Clerk's useAuth() hook. It must run before any hook
 * sends its first request: while rendering a component that renders before the pages,
 * not in a useEffect of a wrapper around them (a wrapper's effects run after its
 * children's).
 */
export function setTokenGetter(getter: TokenGetter): void {
  getToken = getter;
}

// Without a trailing slash, so `${API_URL}${path}` never has a double slash.
const API_URL = env.apiUrl.replace(/\/+$/, '');

/** Sends one request to the API. Orval's generated hooks call this; call those instead. */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = await getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const body = await readBody(response);
  if (!response.ok) {
    if (response.status === 401) {
      unauthorizedHandler();
    }
    throw new ApiError(response.status, body);
  }
  return body as T;
}

export interface UploadProgressEvent {
  loaded: number;
  total: number;
  percent: number;
}

export interface UploadOptions {
  onProgress?: (event: UploadProgressEvent) => void;
  signal?: AbortSignal;
}

/**
 * Uploads multipart form data via XMLHttpRequest to report progress.
 * Adds the API address and Clerk token, dispatches progress updates,
 * and normalizes errors into ApiError (invoking unauthorizedHandler on 401).
 */
export async function uploadWithProgress<T>(
  path: string,
  formData: FormData,
  options: UploadOptions = {},
): Promise<T> {
  const token = await getToken();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}${path}`);
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }

    if (options.signal) {
      if (options.signal.aborted) {
        reject(new DOMException('Upload aborted', 'AbortError'));
        return;
      }
      options.signal.addEventListener('abort', () => {
        xhr.abort();
        reject(new DOMException('Upload aborted', 'AbortError'));
      });
    }

    if (xhr.upload && options.onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          options.onProgress?.({
            loaded: event.loaded,
            total: event.total,
            percent,
          });
        }
      };
    }

    xhr.onload = () => {
      let body: unknown;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        body = xhr.responseText;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T);
      } else {
        if (xhr.status === 401) {
          unauthorizedHandler();
        }
        reject(new ApiError(xhr.status, body));
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error during upload'));
    };

    xhr.send(formData);
  });
}

/** The answer's body: parsed JSON, plain text, or undefined when it is empty. */
async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return undefined;
  }
  const isJson = response.headers.get('Content-Type')?.includes('application/json');
  if (!isJson) {
    return text;
  }
  // A broken JSON body (for example from a proxy error page) is kept as text, so an
  // error answer still becomes an ApiError with its real status.
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
