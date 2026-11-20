// 로그인하고 들어오는 흐름 (009 US3, 013):
// 1) 로그인 전에는 첫 화면(Landing). 버튼을 누르면 Cognito 화면을 건너뛰고 바로 Google로 간다.
// 2) 로그인 뒤 /api/me로 자격(members)을 확인한다. 없으면 초대 코드 화면.
// 3) 코드 통과 → 갱신 토큰으로 새 토큰(그룹 반영)을 받아 바로 대시보드.
// D는 <Dashboard /> 자리에 대시보드를 만든다. 서버 호출은 api.ts의 apiGet(토큰, 경로)을 쓰고,
// ApiError.code === "not_member"면 onNotMember()를 부른다.
import { useCallback, useEffect, useState } from "react";
import { hasAuthParams, useAuth } from "react-oidc-context";
import { ApiError, apiGet } from "./api";
import { cognitoLogoutUrl, signinArgs } from "./auth";
import Invite from "./Invite";
import Landing from "./Landing";

type Membership = "checking" | "member" | "not_member" | { error: string };

export default function App() {
  const auth = useAuth();
  const [membership, setMembership] = useState<Membership>("checking");

  const accessToken = auth.user?.access_token;

  const checkMembership = useCallback(async (token: string) => {
    setMembership("checking");
    try {
      const me = await apiGet<{ sub: string; member: boolean }>(token, "/api/me");
      setMembership(me.member ? "member" : "not_member");
    } catch (e) {
      setMembership({ error: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    if (accessToken) void checkMembership(accessToken);
  }, [accessToken, checkMembership]);

  // 코드 통과 뒤: 그룹이 실린 새 토큰을 받는다. 갱신이 안 되면 다시 로그인(Google 세션이 있어 화면 전환만)
  const onJoined = async () => {
    try {
      const user = await auth.signinSilent();
      if (user) await checkMembership(user.access_token);
    } catch {
      await auth.signinRedirect(signinArgs);
    }
  };

  if (auth.error) {
    return (
      <Shell>
        <p>로그인 중 문제가 생겼습니다: {auth.error.message}</p>
        <button onClick={() => void auth.signinRedirect(signinArgs)}>다시 로그인</button>
      </Shell>
    );
  }

  if (!auth.isAuthenticated || !accessToken) {
    // 로그인에서 막 돌아왔거나(?code=…) 저장된 로그인을 읽는 중이면 잠깐 기다린다
    if (hasAuthParams() || auth.isLoading || auth.activeNavigator) {
      return (
        <Shell>
          <p style={{ textAlign: "center", paddingTop: 96, color: "#666" }}>로그인 중…</p>
        </Shell>
      );
    }
    return <Landing onLogin={() => void auth.signinRedirect(signinArgs)} />;
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
      {membership === "checking" && <p style={{ textAlign: "center", paddingTop: 48 }}>확인 중…</p>}
      {membership === "not_member" && <Invite accessToken={accessToken} email={email} onJoined={() => void onJoined()} />}
      {membership === "member" && <Dashboard accessToken={accessToken} onNotMember={() => setMembership("not_member")} />}
      {typeof membership === "object" && (
        <section style={{ textAlign: "center", paddingTop: 48 }}>
          <p style={{ color: "#666" }}>서버 연결 안 됨: {membership.error} (서버가 꺼져 있으면 정상)</p>
          <button onClick={() => void checkMembership(accessToken)}>다시 확인</button>
        </section>
      )}
    </Shell>
  );
}

function Dashboard({ accessToken, onNotMember }: { accessToken: string; onNotMember: () => void }) {
  const [status, setStatus] = useState<string>("확인 중…");

  useEffect(() => {
    apiGet<{ sub: string }>(accessToken, "/api/me")
      .then((r) => setStatus(`서버 인증 확인됨 (${r.sub.slice(0, 8)}…)`))
      .catch((e: Error) => {
        if (e instanceof ApiError && e.code === "not_member") onNotMember();
        else setStatus(`서버 연결 안 됨: ${e.message}`);
      });
  }, [accessToken, onNotMember]);

  return (
    <section style={{ textAlign: "center", paddingTop: 48 }}>
      <h1>smokestack-guard</h1>
      <p>굴뚝 TMS 대시보드 준비 중</p>
      <p style={{ color: "#666", fontSize: 14 }}>{status}</p>
    </section>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main style={{ fontFamily: "system-ui, sans-serif", padding: "16px", maxWidth: 960, margin: "0 auto" }}>{children}</main>;
}
