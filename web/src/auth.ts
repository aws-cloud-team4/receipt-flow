// Cognito sign-in from the browser (public app client, no secret) or a dev token.
//
// Flow: InitiateAuth(USER_PASSWORD_AUTH) → tokens, or NEW_PASSWORD_REQUIRED for accounts an admin
// created with a temporary password → RespondToAuthChallenge with the user's own password.
// Tokens live in localStorage; the ID token is sent to our APIs, the access token is used only for
// ChangePassword, and the refresh token renews the session and is revoked on sign-out.

export type Role = "employee" | "reviewer" | "admin";

interface Session {
  idToken: string;
  accessToken?: string;
  refreshToken?: string;
  expiresAt: number; // epoch ms
}

export type SignInResult = { status: "signed_in" } | { status: "new_password_required"; session: string };

const KEY = "rf.session";
const EMAIL_KEY = "rf.email";
const MODE = (import.meta.env.VITE_AUTH_MODE ?? "cognito") as "cognito" | "dev";
const REGION = import.meta.env.VITE_REGION ?? "ap-northeast-2";
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";

export const authMode = MODE;

/** Same as the user pool policy in infra/terraform/base/auth.tf. */
export const PASSWORD_RULE = "10자 이상, 영어 소문자와 숫자를 각각 하나 이상";
export function passwordProblem(pw: string): string | null {
  if (pw.length < 10) return "비밀번호는 10자 이상이어야 해요.";
  if (!/[a-z]/.test(pw)) return "영어 소문자를 하나 이상 넣어 주세요.";
  if (!/[0-9]/.test(pw)) return "숫자를 하나 이상 넣어 주세요.";
  return null;
}

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode: kept in memory only */
  }
}

let memory: Session | null = read<Session>(KEY);

function save(s: Session | null) {
  memory = s;
  write(KEY, s);
}

export function rememberedEmail(): string {
  return read<string>(EMAIL_KEY) ?? "";
}

export function rememberEmail(email: string | null) {
  write(EMAIL_KEY, email);
}

const MESSAGES: Record<string, string> = {
  NotAuthorizedException: "이메일 또는 비밀번호가 맞지 않습니다.",
  UserNotFoundException: "이메일 또는 비밀번호가 맞지 않습니다.",
  PasswordResetRequiredException: "비밀번호 재설정이 필요한 계정입니다. 관리자에게 임시 비밀번호를 요청해 주세요.",
  UserNotConfirmedException: "아직 활성화되지 않은 계정입니다. 관리자에게 문의해 주세요.",
  TooManyRequestsException: "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.",
  LimitExceededException: "시도 횟수를 넘었어요. 잠시 후 다시 시도해 주세요.",
  InvalidPasswordException: `비밀번호 규칙에 맞지 않아요 (${PASSWORD_RULE}).`,
  ExpiredCodeException: "로그인 단계가 만료됐어요. 처음부터 다시 로그인해 주세요.",
  CodeMismatchException: "로그인 단계가 만료됐어요. 처음부터 다시 로그인해 주세요.",
};

export class AuthError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function cognito(target: string, body: object) {
  let resp: Response;
  try {
    resp = await fetch(`https://cognito-idp.${REGION}.amazonaws.com/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthError("network", "로그인 서버에 연결할 수 없어요. 네트워크를 확인해 주세요.");
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const type = String(data.__type ?? "").split("#").pop() ?? "";
    const tooManyFailures = type === "NotAuthorizedException" && /attempts exceeded/i.test(data.message ?? "");
    const message = tooManyFailures
      ? "비밀번호를 여러 번 틀려 잠시 잠겼어요. 몇 분 뒤 다시 시도해 주세요."
      : (MESSAGES[type] ?? "로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    throw new AuthError(type || "unknown", message);
  }
  return data;
}

function store(result: { IdToken: string; AccessToken: string; RefreshToken?: string; ExpiresIn: number }) {
  save({
    idToken: result.IdToken,
    accessToken: result.AccessToken,
    refreshToken: result.RefreshToken ?? memory?.refreshToken,
    expiresAt: Date.now() + result.ExpiresIn * 1000,
  });
}

export async function signIn(email: string, password: string): Promise<SignInResult> {
  const data = await cognito("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: CLIENT_ID,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  if (data.ChallengeName === "NEW_PASSWORD_REQUIRED") {
    return { status: "new_password_required", session: data.Session };
  }
  if (data.ChallengeName) {
    throw new AuthError(data.ChallengeName, "지원하지 않는 로그인 단계입니다. 관리자에게 문의해 주세요.");
  }
  store(data.AuthenticationResult);
  return { status: "signed_in" };
}

/** First sign-in with a temporary password: set the user's own password. */
export async function completeNewPassword(email: string, newPassword: string, session: string) {
  const data = await cognito("RespondToAuthChallenge", {
    ChallengeName: "NEW_PASSWORD_REQUIRED",
    ClientId: CLIENT_ID,
    Session: session,
    ChallengeResponses: { USERNAME: email, NEW_PASSWORD: newPassword },
  });
  store(data.AuthenticationResult);
}

export async function changePassword(current: string, next: string) {
  const token = await getToken(); // refreshes the access token when it is about to expire
  if (!token || !memory?.accessToken) throw new AuthError("signed_out", "다시 로그인해 주세요.");
  try {
    await cognito("ChangePassword", {
      AccessToken: memory.accessToken,
      PreviousPassword: current,
      ProposedPassword: next,
    });
  } catch (e) {
    if (e instanceof AuthError && e.code === "NotAuthorizedException") {
      throw new AuthError(e.code, "현재 비밀번호가 맞지 않습니다.");
    }
    throw e;
  }
}

// Header values must be ASCII, so dev users are identified by a short latin id.
export function signInDev(role: Role, id: string) {
  save({ idToken: `dev:dev-${id}:${role}:${id}`, expiresAt: Date.now() + 365 * 86400_000 });
}

/** A developer-login session (test account, no password): password change does not apply. */
export function isDevSession() {
  return memory?.idToken.startsWith("dev:") ?? false;
}

export async function signOut() {
  const refreshToken = memory?.refreshToken;
  save(null);
  if (MODE === "cognito" && refreshToken) {
    // Revoke on the server too, so a copied refresh token stops working. Best effort.
    await cognito("RevokeToken", { Token: refreshToken, ClientId: CLIENT_ID }).catch(() => undefined);
  }
}

export function isSignedIn() {
  return memory !== null;
}

let refreshing: Promise<string | null> | null = null;

async function refresh(s: Session): Promise<string | null> {
  try {
    const data = await cognito("InitiateAuth", {
      AuthFlow: "REFRESH_TOKEN_AUTH",
      ClientId: CLIENT_ID,
      AuthParameters: { REFRESH_TOKEN: s.refreshToken },
    });
    store(data.AuthenticationResult);
    return memory?.idToken ?? null;
  } catch {
    save(null);
    return null;
  }
}

/** ID token for API calls, renewed a minute before it expires (one refresh at a time). */
export async function getToken(force = false): Promise<string | null> {
  const s = memory;
  if (!s) return null;
  if (!force && s.expiresAt - Date.now() > 60_000) return s.idToken;
  if (!s.refreshToken) return force ? null : s.idToken;
  refreshing ??= refresh(s).finally(() => (refreshing = null));
  return refreshing;
}
