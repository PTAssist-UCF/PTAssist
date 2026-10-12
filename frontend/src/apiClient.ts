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
    throw new ApiError(response.status, body);
  }
  return body as T;
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
