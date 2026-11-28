// 초대 코드 입력 화면 (013 US2). 통과하면 onJoined()로 App이 토큰을 새로 받는다.
// D가 대시보드 디자인에 맞춰 모양을 바꿔도 된다. 서버 약속은 contracts/auth-api.md §4
import { useState } from "react";
import { ApiError, apiPost } from "./api";

const MESSAGES: Record<string, string> = {
  invalid_code: "초대 코드가 맞지 않습니다.",
  too_many_attempts: "여러 번 틀렸습니다. 10분 뒤 다시 시도해 주십시오.",
  not_configured: "지금은 초대 코드를 확인할 수 없습니다. 운영자에게 알려 주십시오.",
};

export default function Invite({ accessToken, email, onJoined }: { accessToken: string; email?: string; onJoined: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost<{ member: boolean }>(accessToken, "/api/invite", { code });
      onJoined();
    } catch (err) {
      const c = err instanceof ApiError ? err.code : undefined;
      setError((c && MESSAGES[c]) || `확인 중 문제가 생겼습니다: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={{ maxWidth: 360, margin: "64px auto", textAlign: "center" }}>
      <h1 style={{ fontSize: 22 }}>초대 코드</h1>
      <p style={{ color: "#555", fontSize: 14 }}>
        {email ? `${email} 계정으로 로그인했습니다. ` : ""}처음 한 번만 초대 코드를 입력해 주십시오.
      </p>
      <form onSubmit={(e) => void submit(e)} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="초대 코드"
          autoFocus
          autoComplete="off"
          aria-label="초대 코드"
          style={{ padding: 10, fontSize: 16 }}
        />
        <button type="submit" disabled={busy || !code.trim()} style={{ padding: 10 }}>
          {busy ? "확인 중…" : "확인"}
        </button>
      </form>
      {error && <p role="alert" style={{ color: "#c0392b", fontSize: 14 }}>{error}</p>}
    </section>
  );
}
