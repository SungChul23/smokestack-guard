// Cognito 로그인 설정 (specs/a-platform/009-service-infra, US3)
// 값은 빌드 때 환경 변수로 들어온다. 운영 빌드는 CI가 SSM /tms/app/config/* 에서 읽어 넣는다. 비밀 아님.
import { WebStorageStateStore } from "oidc-client-ts";
import type { SigninRedirectArgs } from "oidc-client-ts";
import type { AuthProviderProps } from "react-oidc-context";

const region = "ap-northeast-2";
const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID as string;
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string;
const loginDomain = import.meta.env.VITE_COGNITO_DOMAIN as string;

export const API_BASE = (import.meta.env.VITE_API_BASE as string) || "https://api.smokestack-guard.store";

export const oidcConfig: AuthProviderProps = {
  authority: `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`,
  client_id: clientId,
  redirect_uri: `${window.location.origin}/`,
  response_type: "code", // + PKCE (라이브러리가 자동)
  scope: "openid email profile",
  // 탭을 닫아도 로그인 유지(Refresh 토큰 30일). 만료된 Access 토큰은 조용히 갱신한다.
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  automaticSilentRenew: true,
  // 로그인 뒤 주소창의 ?code=... 를 지운다
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

// Cognito는 표준 로그아웃 주소를 알려 주지 않아 직접 만든다
export function cognitoLogoutUrl(): string {
  const params = new URLSearchParams({ client_id: clientId, logout_uri: `${window.location.origin}/` });
  return `https://${loginDomain}/logout?${params.toString()}`;
}

// 013: 로그인은 Google만. Cognito 로그인 화면을 건너뛰고 바로 Google로 보낸다 (research R5)
export const LOGIN_PROVIDER = "Google";
export const signinArgs: SigninRedirectArgs = { extraQueryParams: { identity_provider: LOGIN_PROVIDER } };
