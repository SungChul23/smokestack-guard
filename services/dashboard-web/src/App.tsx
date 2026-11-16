// 로그인하고 들어오는 흐름: 토큰이 없으면 바로 Cognito 로그인 페이지로 보낸다(가입 버튼 없음).
// D는 <Dashboard /> 자리에 대시보드를 만든다. 서버 호출은 api.ts의 apiGet(토큰, 경로)을 쓴다.
import { useEffect, useState } from "react";
import { hasAuthParams, useAuth } from "react-oidc-context";
import { apiGet } from "./api";
import { cognitoLogoutUrl } from "./auth";

export default function App() {
  const auth = useAuth();
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (!hasAuthParams() && !auth.isAuthenticated && !auth.activeNavigator && !auth.isLoading && !auth.error && !redirecting) {
      setRedirecting(true);
      void auth.signinRedirect();
    }
  }, [auth, redirecting]);

  if (auth.error) {
    return (
      <Shell>
        <p>로그인 중 문제가 생겼다: {auth.error.message}</p>
        <button onClick={() => void auth.signinRedirect()}>다시 로그인</button>
      </Shell>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <Shell>
        <p>로그인 페이지로 이동하는 중…</p>
      </Shell>
    );
  }

  const email = (auth.user?.profile.email as string | undefined) ?? auth.user?.profile.sub;

  const logout = async () => {
    await auth.removeUser();
    window.location.href = cognitoLogoutUrl();
  };

  return (
    <Shell>
      <header style={{ display: "flex", justifyContent: "flex-end", gap: 12, alignItems: "center" }}>
        <span>{email}</span>
        <button onClick={() => void logout()}>로그아웃</button>
      </header>
      <Dashboard accessToken={auth.user!.access_token} />
    </Shell>
  );
}

function Dashboard({ accessToken }: { accessToken: string }) {
  const [me, setMe] = useState<string>("확인 중…");

  useEffect(() => {
    apiGet<{ sub: string }>(accessToken, "/api/me")
      .then((r) => setMe(`서버 인증 확인됨 (${r.sub.slice(0, 8)}…)`))
      .catch((e: Error) => setMe(`서버 연결 안 됨: ${e.message} (서버가 꺼져 있으면 정상)`));
  }, [accessToken]);

  return (
    <section style={{ textAlign: "center", paddingTop: 48 }}>
      <h1>smokestack-guard</h1>
      <p>굴뚝 TMS 대시보드 준비 중</p>
      <p style={{ color: "#666", fontSize: 14 }}>{me}</p>
    </section>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main style={{ fontFamily: "system-ui, sans-serif", padding: "16px", maxWidth: 960, margin: "0 auto" }}>{children}</main>;
}
