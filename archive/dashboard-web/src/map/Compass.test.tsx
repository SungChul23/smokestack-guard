import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Compass from "./Compass";

describe("방위", () => {
  it("북·동·서·남을 글자로 보이고 화면 낭독용 설명을 하나로 준다", () => {
    const { container } = render(<Compass />);
    const img = screen.getByRole("img", { name: /방위: 위 북 N, 오른쪽 동 E, 왼쪽 서 W, 아래 남 S/ });
    for (const c of ["N", "E", "W", "S"]) expect(img.textContent).toContain(c);
    expect(container.querySelector("svg")).not.toBeNull(); // 십자 별(북쪽 꼭지는 강조색)
  });
});
